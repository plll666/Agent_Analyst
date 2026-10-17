"""Фикстуры тестов воркера.

Тесты помечены ``integration``: им нужны PostgreSQL и ``tla2tools.jar``. Без jar
они пропускаются с явным текстом, а не падают, — иначе юнит-прогон перестал бы
проходить на машине без Java.
"""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.models import ModelVersion, Project, User, Verification
from app.database.session import create_engine_and_sessionmaker, session_scope
from app.worker.artifacts import LocalArtifactStore
from app.worker.main import _SESSIONS_KEY
from app.worker.model_checker import EngineSettings, ModelChecker
from tests.worker.support import JAR, SeededRun


# Область — тест, а не сессия: движок БД привязан к event loop, в котором создан,
# а тесты живут в своём. Сессионная область держала бы соединения из чужого цикла.
@pytest.fixture
async def sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Фабрика сессий на всю сессию тестов."""
    engine, sessionmaker = create_engine_and_sessionmaker()
    yield sessionmaker
    await engine.dispose()


@pytest.fixture
def checker(tmp_path: Path) -> ModelChecker:
    """Движок с коротким таймаутом: тесты не должны висеть из-за перебора."""
    return ModelChecker(
        EngineSettings(
            jar=JAR,
            timeout_seconds=30,
            state_limit=1_000_000,
            workers="1",
            work_dir=tmp_path,
        )
    )


@pytest.fixture
def store(tmp_path: Path) -> LocalArtifactStore:
    """Хранилище артефактов во временном каталоге теста."""
    return LocalArtifactStore(tmp_path / "artifacts")


@pytest.fixture
def worker_ctx(
    sessions: async_sessionmaker[AsyncSession], checker: ModelChecker, store: LocalArtifactStore
) -> dict[str, Any]:
    """Контекст arq с теми же ключами, что и в :func:`app.worker.main.startup`."""
    return {
        _SESSIONS_KEY: sessions,
        "model_checker": checker,
        "artifact_store": store,
        "started": True,
    }


@pytest.fixture
async def seeded_run(sessions: async_sessionmaker[AsyncSession]) -> AsyncIterator[SeededRun]:
    """Проект с версией модели и прогоном в статусе ``PENDING``.

    Создаётся вся цепочка ``users → projects → model_versions → verifications``, и
    строки вставляются именно в этом порядке: в проекте нет ``relationship()``,
    поэтому SQLAlchemy не выстраивает порядок вставок по внешним ключам, и
    пропущенная строка валила бы вставку — так у сокомандника падали DB-тесты.

    Yields:
        Идентификаторы прогона, версии модели и владельца.
    """
    run = SeededRun()
    async with session_scope(sessions) as session:
        session.add(User(id=run.owner_id, email=f"{run.owner_id}@test.local", password_hash="x"))
        await session.flush()
        session.add(Project(id=run.project_id, owner_id=run.owner_id, name="Кейс 2"))
        await session.flush()
        session.add(
            ModelVersion(
                id=run.model_version_id,
                project_id=run.project_id,
                version=1,
                source="manual",
                document={},
                schema_hash="0" * 64,
                validation_status="VALID",
            )
        )
        session.add(
            Verification(
                id=run.verification_id,
                project_id=run.project_id,
                model_version_id=run.model_version_id,
                status="PENDING",
                engine="TLC",
                business_summary="",
            )
        )
    yield run
    async with session_scope(sessions) as session:
        await _delete_run(session, run)


async def _delete_run(session: AsyncSession, run: SeededRun) -> None:
    """Снять цепочку строк в обратном порядке: внешние ключи не дают иначе.

    Args:
        session: Открытая сессия.
        run: Идентификаторы цепочки.
    """
    from sqlalchemy import delete

    from app.database.models import Artifact

    await session.execute(delete(Artifact).where(Artifact.project_id == run.project_id))
    await session.execute(delete(Verification).where(Verification.project_id == run.project_id))
    await session.execute(delete(ModelVersion).where(ModelVersion.project_id == run.project_id))
    await session.execute(delete(Project).where(Project.id == run.project_id))
    await session.execute(delete(User).where(User.id == run.owner_id))
