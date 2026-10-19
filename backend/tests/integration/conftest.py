import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api import analysis
from app.config import get_settings
from app.db import get_session
from app.main import app
from app.repositories import users


def _email(name: str) -> str:
    """Уникальный адрес на прогон."""
    return f"{name}-{uuid.uuid4().hex}@example.com"


def _database_url() -> str:
    """URL базы: ``TEST_DATABASE_URL``, иначе общий ``DATABASE_URL``."""
    return os.environ.get("TEST_DATABASE_URL") or get_settings().database_url


def _probe_database(url: str) -> str:
    """Разобраться с базой до тестов.

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
    """Сессия на настоящем Postgres."""
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
    """Владелец проектов."""
    user = await users.create(session, email=_email("owner"), password_hash="hash")
    return user.id


@pytest_asyncio.fixture
async def stranger_id(session: AsyncSession) -> uuid.UUID:
    """Чужой пользователь."""
    user = await users.create(session, email=_email("stranger"), password_hash="hash")
    return user.id


def case_document() -> dict[str, Any]:
    """Модель из кейса."""
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


@pytest.fixture
def enqueued() -> list[str]:
    """Идентификаторы прогонов, поставленных в очередь вместо arq.

    Тесты не поднимают Redis: HTTP-слой проверяется, а брокер у воркера — отдельно.
    """
    return []


@pytest_asyncio.fixture
async def client(
    session: AsyncSession, enqueued: list[str], monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    """Клиент по приложению: те же роутеры и хендлеры, что и в uvicorn."""

    async def record(verification_id: str, **_kwargs: Any) -> None:
        enqueued.append(verification_id)

    # Подменяется именно в модуле роутера: enqueue_check вызывается напрямую, а не
    # через Depends, поэтому app.dependency_overrides его не увидит.
    monkeypatch.setattr(analysis, "enqueue_check", record)
    app.dependency_overrides[get_session] = lambda: session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def registered(client: httpx.AsyncClient) -> httpx.AsyncClient:
    """Клиент с cookie только что зарегистрированного пользователя."""
    response = await client.post(
        "/api/auth/register",
        json={"email": _email("owner"), "password": "correct-horse", "display_name": "Анна"},
    )
    assert response.status_code == 201, response.text
    assert "session" in response.cookies
    return client
