from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

_engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
_sessionmaker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Сессия с фиксацией: коммит на выходе, откат при исключении."""
    async with _sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Закрыть пул соединений при остановке процесса."""
    await _engine.dispose()
