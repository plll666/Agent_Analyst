from typing import Any

from arq.connections import RedisSettings

from app.worker.model_checker import TLCError, compile_to_tla, run_tlc

REDIS_URL = "redis://redis:6379/0"


async def ping(_ctx: dict[str, Any]) -> str:
    """Проверка живости очереди: задача доходит до воркера и возвращает результат."""
    return "pong"


async def check_behavior(_ctx: dict[str, Any], model: dict[str, Any]) -> dict[str, Any]:
    """Компилирует BehavioralModel в TLA+, запускает TLC с таймаутом, возвращает результат."""
    tla_content, cfg_content = compile_to_tla(model)
    try:
        result = run_tlc(tla_content, cfg_content)
    except TLCError as e:
        return {
            "status": "TIMEOUT" if e.returncode == -1 else "ENGINE_ERROR",
            "engine": "TLC",
            "error_detail": e.stderr or str(e),
        }
    return result


async def startup(ctx: dict[str, Any]) -> None:
    """Подключение к брокеру и подготовка адаптеров."""
    ctx["started"] = True


async def shutdown(ctx: dict[str, Any]) -> None:
    """Аккуратное завершение: закрыть соединения перед остановкой процесса."""
    ctx["started"] = False


class WorkerSettings:
    """Настройки arq. Загружаются командой `arq app.worker.WorkerSettings`."""

    functions: list[Any] = [ping, check_behavior]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(REDIS_URL)
    max_jobs = 1
    job_timeout = 900
