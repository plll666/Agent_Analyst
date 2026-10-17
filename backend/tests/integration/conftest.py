import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.repositories import users


def _database_url() -> str:
    """URL базы для интеграционных тестов.

    ``TEST_DATABASE_URL`` задаёт отдельную базу, иначе берётся общий ``DATABASE_URL``.
    Тесты пишут строки и не чистят их, поэтому указывать на рабочую базу приложения
    не стоит.
    """
    return os.environ.get("TEST_DATABASE_URL") or get_settings().database_url


def _probe_database(url: str) -> str:
    """Разобраться с базой до тестов: недоступна, не мигрирована или готова.

    Returns:
        ``"unavailable"``, ``"unmigrated"`` или ``"ready"``.
    """
    from sqlalchemy.exc import SQLAlchemyError

    async def probe() -> str:
        engine = create_async_engine(url)
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
        except SQLAlchemyError as error:
            if "alembic_version" in str(error):
                return "unmigrated"
            return "unavailable"
        finally:
            await engine.dispose()
        return "ready"

    try:
        return asyncio.run(probe())
    except OSError:
        return "unavailable"


@pytest.fixture(scope="session")
def database_url() -> str:
    return _database_url()


@pytest.fixture(scope="session")
def database_state(database_url: str) -> str:
    return _probe_database(database_url)


@pytest_asyncio.fixture
async def session(database_state: str, database_url: str) -> AsyncIterator[AsyncSession]:
    """Сессия на настоящем Postgres.

    Каждый тест заводит своих пользователей, поэтому порядок и число прогонов
    на результат не влияют.
    """
    if database_state == "unavailable":
        pytest.skip(f"Postgres недоступен по {database_url}")
    if database_state == "unmigrated":
        pytest.fail(f"По {database_url} нет alembic_version — выполните `alembic upgrade head`")

    engine = create_async_engine(database_url)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as open_session:
        yield open_session
        await open_session.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def owner_id(session: AsyncSession) -> uuid.UUID:
    """Владелец проектов. Реальный пользователь: на ``projects.owner_id`` сторит FK."""
    user = await users.create(
        session, email=f"owner-{uuid.uuid4().hex}@example.com", password_hash="hash"
    )
    return user.id


@pytest_asyncio.fixture
async def stranger_id(session: AsyncSession) -> uuid.UUID:
    """Чужой пользователь: проверяет, что данные отфильтровываются по владельцу."""
    user = await users.create(
        session, email=f"stranger-{uuid.uuid4().hex}@example.com", password_hash="hash"
    )
    return user.id


def case_document() -> dict[str, Any]:
    """Модель из кейса: репозиторию она безразлична, важен только факт round-trip."""
    return {
        "variables": [
            {"name": "status", "type": "enum", "values": ["Created", "Cancelled"]},
            {"name": "approved", "type": "boolean"},
        ],
        "initial": {"status": "Created", "approved": False},
        "transitions": [
            {
                "name": "Cancel",
                "guard": {"eq": [{"var": "status"}, "Created"]},
                "effects": [{"set": ["status", "Cancelled"]}],
            }
        ],
        "properties": [{"id": "P1", "type": "reachable", "expression": {"var": "status"}}],
    }
