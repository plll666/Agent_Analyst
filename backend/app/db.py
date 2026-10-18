"""Сессия БД для HTTP-слоя поверх общей реализации из ``app.database.session``."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.database.session import create_engine_and_sessionmaker
from app.database.session import session_scope as db_session_scope

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def open_database() -> None:
    """Создать движок и фабрику сессий."""
    global _engine, _sessionmaker
    _engine, _sessionmaker = create_engine_and_sessionmaker()


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession]:
    """Сессия с коммитом на выходе и откатом при ошибке."""
    if _sessionmaker is None:
        raise RuntimeError("open_database() не вызван: фабрика сессий не создана")
    async with db_session_scope(_sessionmaker) as session:
        yield session


async def get_session() -> AsyncGenerator[AsyncSession]:
    """Зависимость FastAPI: сессия на запрос."""
    async with session_scope() as session:
        yield session


async def dispose_engine() -> None:
    """Закрыть пул соединений при остановке процесса."""
    if _engine is not None:
        await _engine.dispose()
