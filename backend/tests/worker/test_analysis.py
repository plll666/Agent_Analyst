"""Итерация агента в воркере: модель, проверка, объяснение, запись в базу."""

import uuid
from typing import Any

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.models import ModelVersion, Requirement, Verification
from app.database.session import session_scope
from app.worker.main import _LLM_KEY, run_analysis
from tests.agent.support import FakeLLM, cited_payload, explanation_payload
from tests.worker.support import acceptance_model

pytestmark = pytest.mark.integration

REQUIREMENT = (
    "Заявка после согласования может быть исполнена. "
    "Пользователь может отменить заявку до исполнения."
)
QUOTE = "Пользователь может отменить заявку до исполнения."


@pytest.fixture
async def analysis_run(
    sessions: async_sessionmaker[AsyncSession],
) -> Any:
    """Проект с требованием и прогоном, у которого модели ещё нет."""
    owner_id = uuid.uuid4()
    project_id = uuid.uuid4()
    requirement_id = uuid.uuid4()
    verification_id = uuid.uuid4()
    async with session_scope(sessions) as session:
        from app.database.models import Project, User

        session.add(User(id=owner_id, email=f"{owner_id}@test.local", password_hash="x"))
        await session.flush()
        session.add(Project(id=project_id, owner_id=owner_id, name="Кейс 2"))
        await session.flush()
        session.add(
            Requirement(
                id=requirement_id,
                project_id=project_id,
                version=1,
                raw_text=REQUIREMENT,
                is_current=True,
            )
        )
        session.add(
            Verification(
                id=verification_id,
                project_id=project_id,
                model_version_id=None,
                requirement_id=requirement_id,
                status="PENDING",
                engine="TLC",
                business_summary="",
            )
        )
    yield verification_id
    async with session_scope(sessions) as session:
        from sqlalchemy import delete

        from app.database.models import Artifact

        await session.execute(delete(Artifact).where(Artifact.project_id == project_id))
        await session.execute(delete(Verification).where(Verification.project_id == project_id))
        await session.execute(delete(ModelVersion).where(ModelVersion.project_id == project_id))
        await session.execute(delete(Requirement).where(Requirement.project_id == project_id))
        await session.execute(delete(Project).where(Project.id == project_id))
        await session.execute(delete(User).where(User.id == owner_id))


def _payload() -> dict[str, Any]:
    """Ответ модели: документ модели с цитатами на каждом правиле."""
    return cited_payload(acceptance_model(fixed=False), QUOTE)


async def test_analysis_builds_model_checks_it_and_explains(
    sessions: async_sessionmaker[AsyncSession],
    worker_ctx: dict[str, Any],
    analysis_run: uuid.UUID,
) -> None:
    """Одна задача ведёт цикл целиком и записывает и модель, и результат."""
    client = FakeLLM(_payload(), explanation_payload())
    ctx = {**worker_ctx, _LLM_KEY: client}

    status = await run_analysis(ctx, str(analysis_run))

    assert status == "PROPERTY_VIOLATED"
    async with session_scope(sessions) as session:
        run = await session.get(Verification, analysis_run)
        assert run is not None
        assert run.status == "PROPERTY_VIOLATED"
        assert run.model_version_id is not None
        assert run.hypothesis
        assert run.question
        assert run.root_cause == "REQUIREMENT_ERROR"
        assert run.business_summary

        version = await session.get(ModelVersion, run.model_version_id)
        assert version is not None
        assert version.source == "agent"
        assert version.requirement_id is not None
        assert version.document["initial"]["status"] == "Created"
        assert version.document["initial"]["cancelled"] is False


async def test_analysis_without_provider_ends_with_agent_error(
    sessions: async_sessionmaker[AsyncSession],
    worker_ctx: dict[str, Any],
    analysis_run: uuid.UUID,
) -> None:
    """Без провайдера итерация честно останавливается, а не висит в PENDING."""
    status = await run_analysis(worker_ctx, str(analysis_run))

    assert status == "AGENT_ERROR"
    async with session_scope(sessions) as session:
        run = await session.get(Verification, analysis_run)
        assert run is not None
        assert run.status == "AGENT_ERROR"
        assert run.model_version_id is None
        assert run.business_summary


async def test_analysis_records_artifacts_for_reproduction(
    sessions: async_sessionmaker[AsyncSession],
    worker_ctx: dict[str, Any],
    analysis_run: uuid.UUID,
) -> None:
    """Артефакты прогона сохраняются: по ним проверку можно повторить руками."""
    client = FakeLLM(_payload(), explanation_payload())
    ctx = {**worker_ctx, _LLM_KEY: client}

    await run_analysis(ctx, str(analysis_run))

    async with session_scope(sessions) as session:
        from app.database.models import Artifact

        artifacts = list(
            await session.scalars(select(Artifact).where(Artifact.project_id.is_not(None)))
        )
        assert artifacts


async def test_analysis_checks_snapshotted_requirement(
    sessions: async_sessionmaker[AsyncSession],
    worker_ctx: dict[str, Any],
    analysis_run: uuid.UUID,
) -> None:
    """Прогон держит выбранную версию требования независимо от «текущей».

    Пользователь успел дописать уточнение в проект, пока задача стояла в очереди:
    воркер обязан строить модель по тексту на момент запуска, а не по новому.
    """
    async with session_scope(sessions) as session:
        record = await session.get(Verification, analysis_run)
        assert record is not None
        newer = Requirement(
            id=uuid.uuid4(),
            project_id=record.project_id,
            version=2,
            raw_text=REQUIREMENT + "\n\nУточнение пользователя: совсем другой текст.",
            is_current=True,
        )
        session.add(newer)
        previous = await session.scalar(
            select(Requirement.id).where(
                Requirement.project_id == record.project_id,
                Requirement.version == 1,
            )
        )
        assert previous is not None
        await session.execute(
            update(Requirement).where(Requirement.id == previous).values(is_current=False)
        )

    client = FakeLLM(_payload(), explanation_payload())
    ctx = {**worker_ctx, _LLM_KEY: client}

    await run_analysis(ctx, str(analysis_run))

    prompt = client.calls[0]["user"]
    assert "Уточнение пользователя: совсем другой текст" not in prompt
    assert "Пользователь может отменить заявку до исполнения" in prompt
