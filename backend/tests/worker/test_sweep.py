"""Надёжность очереди: свип зависших PENDING и finalizer упавшей задачи.

Строка прогона в статусе ``PENDING`` — собственный «outbox»: постановка задачи
в broker не входит в транзакцию коммита, поэтому её можно потерять. Свип обязан
перевставлять такие прогоны, а по дедлайну — закрывать их ``ENGINE_ERROR``.

Broker в этих тестах подделан: Redis не нужен, проверяется логика решений свипа,
а не соединение.
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import pytest
from arq.jobs import JobStatus
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.models import Project, User, Verification
from app.database.session import session_scope
from app.domain.explanation import summary_for
from app.domain.verification import VerificationStatus
from app.worker.main import (
    _SESSIONS_KEY,
    _finalize_crashed,
    _finalize_stale,
    _job_status,
    _pending_rows,
    _sweep_pending,
)

pytestmark = pytest.mark.integration


class FakePool:
    """Подменённый broker: запоминает постановки, имитирует создание задачи."""

    def __init__(self) -> None:
        self.enqueued: list[tuple[str, str]] = []

    async def enqueue_job(self, function: str, verification_id: str, **_kwargs: Any) -> object:
        self.enqueued.append((function, verification_id))
        return object()  # arq отдаёт None только для уже стоящей задачи


@pytest.fixture
def fake_pool() -> FakePool:
    """Broker без сети: постановки записываются, повторов arq не имитирует."""
    return FakePool()


@pytest.fixture
def sweep_ctx(sessions: async_sessionmaker[AsyncSession], fake_pool: FakePool) -> dict[str, Any]:
    """Контекст arq для свипа: сессии и подменённый broker."""
    return {_SESSIONS_KEY: sessions, "redis": fake_pool}


@dataclass
class Queued:
    """Идентификаторы созданной цепочки прогона."""

    verification_id: uuid.UUID
    project_id: uuid.UUID


@pytest.fixture
async def queued_run(
    sessions: async_sessionmaker[AsyncSession],
) -> AsyncIterator[Queued]:
    """Проект с прогоном ``PENDING`` без версии модели — как у агентного цикла.

    Yields:
        Идентификаторы прогона и проекта.
    """
    owner_id = uuid.uuid4()
    project_id = uuid.uuid4()
    verification_id = uuid.uuid4()
    async with session_scope(sessions) as session:
        session.add(User(id=owner_id, email=f"{owner_id}@test.local", password_hash="x"))
        await session.flush()
        session.add(Project(id=project_id, owner_id=owner_id, name="Свип"))
        await session.flush()
        session.add(
            Verification(
                id=verification_id,
                project_id=project_id,
                model_version_id=None,
                status="PENDING",
                engine="TLC",
                business_summary="",
            )
        )
    run = Queued(verification_id=verification_id, project_id=project_id)
    yield run
    async with session_scope(sessions) as session:
        from sqlalchemy import delete

        from app.database.models import Artifact

        await session.execute(delete(Artifact).where(Artifact.project_id == project_id))
        await session.execute(delete(Verification).where(Verification.project_id == project_id))
        await session.execute(delete(Project).where(Project.id == project_id))
        await session.execute(delete(User).where(User.id == owner_id))


@pytest.fixture(autouse=True)
def scoped_pending_rows(
    monkeypatch: pytest.MonkeyPatch, sessions: async_sessionmaker[AsyncSession], queued_run: Queued
) -> None:
    """Свип видит только строки этого теста.

    База общая: другие тесты-наборы могли оставить в ней строки ``PENDING``
    прямо сейчас. Свип честно обрабатывает всю базу, у теста же запрос
    к ``verifications`` ограничивается созданным здесь проектом.
    """

    async def scoped(sessionmaker: async_sessionmaker[AsyncSession], older_than: Any) -> Any:
        rows = await _pending_rows(sessionmaker, older_than)
        return [row for row in rows if row.project_id == queued_run.project_id]

    monkeypatch.setattr("app.worker.main._pending_rows", scoped)
    _ = sessions


async def _age(
    sessions: async_sessionmaker[AsyncSession], verification_id: uuid.UUID, seconds: float
) -> None:
    """Состарить прогон: постановка задачи после коммита уже завершилась."""
    async with session_scope(sessions) as session:
        await session.execute(
            update(Verification)
            .where(Verification.id == verification_id)
            .values(created_at=datetime.now().astimezone() - timedelta(seconds=seconds))
        )


async def test_sweep_requeues_lost_run(
    sweep_ctx: dict[str, Any],
    fake_pool: FakePool,
    sessions: async_sessionmaker[AsyncSession],
    queued_run: Queued,
) -> None:
    """Потерянный прогон перевставляется как ``run_analysis`` и считается в счётчике."""
    await _age(sessions, queued_run.verification_id, 60.0)

    handled = await _sweep_pending(sweep_ctx)

    assert handled == 1
    assert fake_pool.enqueued == [("run_analysis", str(queued_run.verification_id))]


async def test_sweep_requeue_keeps_reasoning_choice(
    sweep_ctx: dict[str, Any],
    fake_pool: FakePool,
    sessions: async_sessionmaker[AsyncSession],
    queued_run: Queued,
) -> None:
    """Выбранный пользователем режим рассуждений не теряется при перевставке."""
    await _age(sessions, queued_run.verification_id, 60.0)
    async with session_scope(sessions) as session:
        await session.execute(
            update(Verification)
            .where(Verification.id == queued_run.verification_id)
            .values(reasoning=True)
        )

    await _sweep_pending(sweep_ctx)

    assert fake_pool.enqueued == [("run_analysis", str(queued_run.verification_id))]


async def test_sweep_does_not_count_zero_interventions(
    sweep_ctx: dict[str, Any], fake_pool: FakePool
) -> None:
    """Прогон вне порога возраста не трогается вовсе: вмешательства ноль."""
    handled = await _sweep_pending(sweep_ctx)

    assert handled == 0
    assert fake_pool.enqueued == []


async def test_sweep_skips_active_jobs(
    sweep_ctx: dict[str, Any],
    fake_pool: FakePool,
    monkeypatch: pytest.MonkeyPatch,
    sessions: async_sessionmaker[AsyncSession],
    queued_run: Queued,
) -> None:
    """Прогон с активной задачей свип не перевставляет: вмешательства ноль."""

    async def active(_pool: Any, job_id: str) -> JobStatus:
        assert job_id == str(queued_run.verification_id)
        return JobStatus.queued

    monkeypatch.setattr("app.worker.main._job_status", active)

    await _age(sessions, queued_run.verification_id, 60.0)
    handled = await _sweep_pending(sweep_ctx)

    assert handled == 0
    assert fake_pool.enqueued == []


async def test_sweep_finalizes_stale_run(
    sweep_ctx: dict[str, Any],
    fake_pool: FakePool,
    sessions: async_sessionmaker[AsyncSession],
    queued_run: Queued,
) -> None:
    """Прогон вне дедлайна закрывается честным ``ENGINE_ERROR``, а не висит."""
    await _age(sessions, queued_run.verification_id, 4000.0)

    handled = await _sweep_pending(sweep_ctx)

    assert handled == 1
    assert fake_pool.enqueued == []
    async with session_scope(sessions) as session:
        row = await session.get(Verification, queued_run.verification_id)
        assert row is not None
        assert row.status == "ENGINE_ERROR"
        assert row.engine == "NONE"
        assert row.error_detail


async def test_finalize_stale_does_not_overwrite_terminal(
    sessions: async_sessionmaker[AsyncSession],
    queued_run: Queued,
) -> None:
    """Прогон, завершившийся между выборкой и записью, свип не перезаписывает."""
    async with session_scope(sessions) as session:
        await session.execute(
            update(Verification)
            .where(Verification.id == queued_run.verification_id)
            .values(
                status="PROPERTY_HOLDS",
                engine="TLC",
                business_summary=summary_for(VerificationStatus.PROPERTY_HOLDS),
            )
        )
    row = await session.get(Verification, queued_run.verification_id)
    assert row is not None

    closed = await _finalize_stale(sessions, row)

    assert closed is False
    async with session_scope(sessions) as session:
        after = await session.get(Verification, queued_run.verification_id)
        assert after is not None
        assert after.status == "PROPERTY_HOLDS"


async def test_finalize_crashed_writes_engine_error(
    sessions: async_sessionmaker[AsyncSession],
    queued_run: Queued,
) -> None:
    """Упавшая задача оставляет в базе отказ, а не молчаливое PENDING."""
    await _finalize_crashed(sessions, queued_run.verification_id, "итерация упала: TestCrash")

    async with session_scope(sessions) as session:
        row = await session.get(Verification, queued_run.verification_id)
        assert row is not None
        assert row.status == "ENGINE_ERROR"
        assert row.engine == "NONE"
        assert "TestCrash" in (row.error_detail or "")


async def test_job_status_survives_broker_malfunction() -> None:
    """Недоступный broker не роняет свип: статус читается как «неизвестно»."""

    class BrokenPool:
        def __getattr__(self, name: str) -> Any:
            raise RuntimeError("redis недоступен")

    status = await _job_status(BrokenPool(), str(uuid.uuid4()))

    assert status is None
