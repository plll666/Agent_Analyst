"""ARQ worker settings and tasks."""

from typing import Any

from arq.connections import RedisSettings

from app.worker.db import (
    create_engine_and_sessionmaker,
    get_tlc_version,
    get_verification_model,
    save_verification_result,
)
from app.worker.model_checker import TLCError, compile_to_tla, run_tlc

REDIS_URL = "redis://redis:6379/0"


async def ping(_ctx: dict[str, Any]) -> str:
    """Проверка живости очереди: задача доходит до воркера и возвращает результат."""
    return "pong"


async def startup(ctx: dict[str, Any]) -> None:
    """Подключение к брокеру и подготовка адаптеров."""
    engine, sessionmaker = create_engine_and_sessionmaker()
    ctx["db_engine"] = engine
    ctx["db_sessionmaker"] = sessionmaker
    ctx["tlc_version"] = await get_tlc_version()
    ctx["started"] = True


async def shutdown(ctx: dict[str, Any]) -> None:
    """Аккуратное завершение: закрыть соединения перед остановкой процесса."""
    engine = ctx.get("db_engine")
    if engine:
        await engine.dispose()
    ctx["started"] = False


async def check_behavior(ctx: dict[str, Any], verification_id: str) -> dict[str, Any]:
    """Компилирует BehavioralModel в TLA+, запускает TLC с таймаутом, сохраняет результат в БД."""
    sessionmaker = ctx["db_sessionmaker"]

    model_data = await get_verification_model(sessionmaker, verification_id)
    if not model_data:
        result = {
            "status": "ENGINE_ERROR",
            "engine": "TLC",
            "engine_version": ctx.get("tlc_version", "TLC 1.7.4"),
            "error_detail": f"Verification {verification_id} not found",
            "duration_ms": 0,
            "counterexample": None,
            "statistics": {},
            "business_summary": "",
        }
        await save_verification_result(sessionmaker, verification_id, result)
        return result

    model = model_data["document"]
    tla_content, cfg_content = compile_to_tla(model)

    try:
        result = run_tlc(tla_content, cfg_content)
    except TLCError as e:
        result = {
            "status": "TIMEOUT" if e.returncode == -1 else "ENGINE_ERROR",
            "engine": "TLC",
            "engine_version": ctx.get("tlc_version", "TLC 1.7.4"),
            "error_detail": e.stderr or str(e),
            "duration_ms": 0,
            "counterexample": None,
            "statistics": {},
            "business_summary": "",
        }

    result["business_summary"] = result.get("business_summary", "")
    await save_verification_result(sessionmaker, verification_id, result)
    return result


class WorkerSettings:
    """Настройки arq. Загружаются командой `arq app.worker.WorkerSettings`."""

    functions: list[Any] = [ping, check_behavior]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(REDIS_URL)
    max_jobs = 1
    job_timeout = 900
