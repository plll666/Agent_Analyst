from typing import Any

from arq.connections import RedisSettings

REDIS_URL = "redis://redis:6379/0"


async def ping(_ctx: dict[str, Any]) -> str:
    """Проверка живости очереди: задача доходит до воркера и возвращает результат."""
    return "pong"


async def startup(ctx: dict[str, Any]) -> None:
    """Подключение к брокеру и подготовка адаптеров."""
    ctx["started"] = True


async def shutdown(ctx: dict[str, Any]) -> None:
    """Аккуратное завершение: закрыть соединения перед остановкой процесса."""
    ctx["started"] = False


class WorkerSettings:
    """Настройки arq. Загружаются командой `arq app.worker.WorkerSettings`."""

    functions: list[Any] = [ping]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(REDIS_URL)
    max_jobs = 1
    job_timeout = 900
