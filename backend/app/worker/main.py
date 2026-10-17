"""Фоновые задачи arq: проверка модели и запись результата.

Задача получает идентификатор строки ``verifications``, а не саму модель: модель
читается из БД по ``model_version_id``, поэтому воркер работает ровно с тем
документом, который агент положил в базу, и не может проверить другую версию.
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from arq.connections import RedisSettings
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.database.session import create_engine_and_sessionmaker
from app.domain.behavioral_model import BehavioralModel
from app.domain.verdict import combine
from app.domain.verification import VerificationResult, VerificationStatus
from app.worker.artifacts import LocalArtifactStore, RunArtifacts
from app.worker.model_checker import EngineSettings, ModelChecker
from app.worker.repository import (
    RunContext,
    VerificationNotFoundError,
    load_run_context,
    save_artifact_rows,
    save_result,
)

logger = logging.getLogger(__name__)

REDIS_URL = "redis://redis:6379/0"
ENGINE_WHEN_NOT_RUN = "TLC"

_ENGINE_KEY = "model_checker"
_STORE_KEY = "artifact_store"
_SESSIONS_KEY = "db_sessionmaker"


class CheckBehaviorError(RuntimeError):
    """Проверку выполнить нельзя и записать результат некуда.

    Отдельный тип нужен, чтобы arq пометил задачу как упавшую: молчаливый выход
    оставил бы строку в ``PENDING`` навсегда, и фронт опрашивал бы её до
    бесконечности.
    """


@dataclass(frozen=True, slots=True)
class CheckReport:
    """Результат прогона и текст, который увидит пользователь."""

    result: VerificationResult
    summary: str


async def ping(_ctx: dict[str, Any]) -> str:
    """Проверка живости очереди: задача доходит до воркера и возвращает результат."""
    return "pong"


async def check_behavior(ctx: dict[str, Any], verification_id: str) -> str:
    """Проверить свойства модели прогона и записать результат.

    Свойства проверяются по одному: у результата одно поле ``property_id``, и по
    пачке свойств нельзя честно сказать, какое именно сработало. Прогоны сводятся
    в один результат по правилам ``app.domain.verdict``.

    Args:
        ctx: Контекст arq с адаптерами, подготовленными в :func:`startup`.
        verification_id: Идентификатор строки ``verifications``.

    Returns:
        Терминальный статус строкой: он же попадает в лог задачи, и по нему видно,
        чем закончился прогон, не открывая БД.

    Raises:
        CheckBehaviorError: если строки прогона нет либо сохранить результат не
            удалось. В обоих случаях результат записать некуда, и arq должен
            увидеть падение, а не тихий успех.
    """
    sessionmaker = ctx[_SESSIONS_KEY]
    checker: ModelChecker = ctx[_ENGINE_KEY]
    store: LocalArtifactStore = ctx[_STORE_KEY]
    identifier = uuid.UUID(verification_id)

    try:
        run = await load_run_context(sessionmaker, identifier)
    except VerificationNotFoundError as missing:
        raise CheckBehaviorError(str(missing)) from missing

    report = await _check_model(sessionmaker, checker, store, run)
    try:
        await save_result(sessionmaker, run, report.result, report.summary)
    except VerificationNotFoundError as missing:
        raise CheckBehaviorError(str(missing)) from missing

    logger.info(
        "прогон %s: статус %s, свойство %s",
        verification_id,
        report.result.status,
        report.result.property_id,
    )
    return str(report.result.status)


async def _check_model(
    sessionmaker: async_sessionmaker[AsyncSession],
    checker: ModelChecker,
    store: LocalArtifactStore,
    run: RunContext,
) -> CheckReport:
    """Прогнать движок по каждому свойству, сохранить артефакты и свести результаты."""
    try:
        model = BehavioralModel.model_validate(run.document)
    except ValidationError as invalid:
        result = VerificationResult(
            status=VerificationStatus.MODEL_INVALID,
            engine=ENGINE_WHEN_NOT_RUN,
            error_detail=f"документ модели не прошёл валидацию: {invalid}",
        )
        return CheckReport(result=result, summary=summary_for(result))

    outcomes = [await checker.check(model, prop) for prop in model.properties]
    stored = store.save_run(
        str(run.verification_id),
        [
            RunArtifacts(
                property_id=prop.id,
                spec=outcome.spec.tla,
                cfg=outcome.spec.cfg,
                output=outcome.output,
            )
            for prop, outcome in zip(model.properties, outcomes, strict=True)
        ],
    )
    await save_artifact_rows(sessionmaker, run, stored)
    result = combine([outcome.result for outcome in outcomes])
    return CheckReport(result=result, summary=summary_for(result))


def summary_for(result: VerificationResult) -> str:
    """Объяснение статуса на языке пользователя.

    Пишется, пока объяснения от агента ещё нет: контракт требует непустое
    ``business_summary`` у любого терминального прогона, а пустая строка рядом со
    статусом ``ENGINE_ERROR`` читалась бы как «всё хорошо». Когда появится агент,
    он заменит эти тексты сценарием на языке требований.

    Args:
        result: Результат проверки.

    Returns:
        Текст объяснения.
    """
    return _SUMMARIES[result.status]


_SUMMARIES: dict[VerificationStatus, str] = {
    VerificationStatus.PROPERTY_HOLDS: (
        "В исследованной модели нарушений не нашлось. Это не доказательство "
        "корректности системы: проверена только построенная модель."
    ),
    VerificationStatus.PROPERTY_VIOLATED: (
        "Найден контрпример — последовательность, нарушающая проверяемое свойство."
    ),
    VerificationStatus.MODEL_INVALID: (
        "Модель не прошла валидацию или не компилируется в TLA+, перебор не начался."
    ),
    VerificationStatus.TIMEOUT: "Движок не уложился в лимит времени, проверка не завершена.",
    VerificationStatus.STATE_LIMIT_REACHED: (
        "Исчерпан лимит состояний, перебор остановлен до конца."
    ),
    VerificationStatus.ENGINE_ERROR: "Движок завершился с ошибкой, результата проверки нет.",
    VerificationStatus.PENDING: "Проверка ещё выполняется.",
}


async def startup(ctx: dict[str, Any]) -> None:
    """Подключение к брокеру и подготовка адаптеров."""
    engine, sessionmaker = create_engine_and_sessionmaker()
    ctx["db_engine"] = engine
    ctx[_SESSIONS_KEY] = sessionmaker
    ctx[_ENGINE_KEY] = ModelChecker(EngineSettings.from_env())
    ctx[_STORE_KEY] = LocalArtifactStore.from_env()
    ctx["started"] = True


async def shutdown(ctx: dict[str, Any]) -> None:
    """Аккуратное завершение: отпустить соединения перед остановкой процесса."""
    engine: AsyncEngine | None = ctx.pop("db_engine", None)
    if engine is not None:
        await engine.dispose()
    ctx["started"] = False


class WorkerSettings:
    """Настройки arq. Загружаются командой `arq app.worker.main.WorkerSettings`."""

    functions: list[Any] = [ping, check_behavior]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(REDIS_URL)
    max_jobs = 1
    job_timeout = 900
