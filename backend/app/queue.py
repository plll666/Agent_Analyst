"""Пул arq: HTTP-слой кладёт сюда задачи на проверку."""

import logging
from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.config import get_settings

logger = logging.getLogger(__name__)

CHECK_BEHAVIOR = "check_behavior"
RUN_ANALYSIS = "run_analysis"

_pool: ArqRedis | None = None


async def open_queue() -> None:
    """Подключиться к брокеру."""
    global _pool
    settings = get_settings()
    _pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))


async def close_queue() -> None:
    """Закрыть соединение с брокером."""
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


async def enqueue_check(verification_id: str, **kwargs: Any) -> None:
    """Поставить прогон в очередь по его идентификатору.

    ``job_id`` равен идентификатору прогона: повторная постановка не создаст
    дубль задачи, поэтому потерянный воркером прогон можно перевставить.
    """
    if _pool is None:
        raise RuntimeError("очередь не открыта: open_queue() не вызван")
    job = await _pool.enqueue_job(
        CHECK_BEHAVIOR, verification_id, _job_id=verification_id, **kwargs
    )
    if job is not None:
        logger.info("прогон %s поставлен в очередь", verification_id)


async def enqueue_analysis(verification_id: str, **kwargs: Any) -> None:
    """Поставить итерацию агента в очередь по идентификатору прогона.

    ``job_id`` равен идентификатору прогона: повторная постановка не создаст
    дубль задачи, поэтому потерянный воркером прогон можно перевставить.
    """
    if _pool is None:
        raise RuntimeError("очередь не открыта: open_queue() не вызван")
    job = await _pool.enqueue_job(RUN_ANALYSIS, verification_id, _job_id=verification_id, **kwargs)
    if job is not None:
        logger.info("итерация агента по прогону %s поставлена в очередь", verification_id)
