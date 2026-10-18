import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_EXAMPLE = "postgresql+asyncpg://agent_analyst:agent_analyst@localhost:5432/agent_analyst"


def get_database_url() -> str:
    """Строка подключения из переменной ``DATABASE_URL``.

    Returns:
        Строка подключения из окружения.

    Raises:
        RuntimeError: если переменная не задана. Падать нужно сразу и с понятным
            текстом: без БД не работают ни миграции, ни фоновая задача, а
            молчаливый дефолт увёл бы проверку в ``ENGINE_ERROR``.
    """
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL не задан. Пример: "
            f"{_EXAMPLE}. Внутри compose переменная уже собрана из POSTGRES_*."
        )
    return url


def create_engine_and_sessionmaker() -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """Создать движок и фабрику сессий.

    ``expire_on_commit=False`` — после коммита объект остаётся пригодным для
    чтения: фоновая задача возвращает результат наружу уже после записи в БД, и
    без этого флага он бы попытался перечитать закрытую сессию.

    Returns:
        Движок и фабрика сессий; движок нужно освободить через ``dispose``.
    """
    engine = create_async_engine(get_database_url(), pool_pre_ping=True)
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def session_scope(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Сессия с фиксацией при успехе и откатом при любой ошибке.

    Коммит здесь, а не в вызывающем коде: иначе два места записи в БД разъедутся
    по транзакции, и одна из них забудет откатить неудачную.

    Args:
        sessionmaker: Фабрика сессий воркера или миграции.

    Yields:
        Открытая сессия; по выходу из блока она закрыта.
    """
    async with sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
