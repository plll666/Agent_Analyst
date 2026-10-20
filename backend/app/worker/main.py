"""Фоновые задачи arq: проверка модели, объяснение и запись результата.

Задача получает идентификатор строки ``verifications``, а не саму модель: модель
читается из БД по ``model_version_id``, поэтому воркер работает ровно с тем
документом, который агент положил в базу, и не может проверить другую версию.

Движок и агент остаются разными компонентами: ``ModelChecker`` не знает про LLM,
а объяснение вызывается уже после того, как статус получен. Если LLM недоступна,
результат движка всё равно записывается с честным шаблонным текстом — проверка не
должна пропадать из-за провайдера.
"""

import logging
import uuid
from typing import Any

from arq.connections import RedisSettings
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agent.explainer import explain_result
from app.agent.llm import LLMClient, LLMError, LLMSettings, client_from_env
from app.database.session import create_engine_and_sessionmaker
from app.domain.behavioral_model import BehavioralModel
from app.domain.explanation import summary_for
from app.domain.verdict import combine
from app.domain.verification import (
    VerificationExplanation,
    VerificationResult,
    VerificationStatus,
)
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
_LLM_KEY = "llm_client"


class CheckBehaviorError(RuntimeError):
    """Проверку выполнить нельзя и записать результат некуда.

    Отдельный тип нужен, чтобы arq пометил задачу как упавшую: молчаливый выход
    оставил бы строку в ``PENDING`` навсегда, и фронт опрашивал бы её до
    бесконечности.
    """


async def ping(_ctx: dict[str, Any]) -> str:
    """Проверка живости очереди: задача доходит до воркера и возвращает результат."""
    return "pong"


async def check_behavior(ctx: dict[str, Any], verification_id: str) -> str:
    """Проверить свойства модели, объяснить результат и записать его.

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

    result = await _check_model(sessionmaker, checker, store, run)
    result, explanation = await _explain(ctx, run, result)
    try:
        await save_result(sessionmaker, run, result, explanation)
    except VerificationNotFoundError as missing:
        raise CheckBehaviorError(str(missing)) from missing

    logger.info(
        "прогон %s: статус %s, свойство %s",
        verification_id,
        result.status,
        result.property_id,
    )
    return str(result.status)


async def _check_model(
    sessionmaker: async_sessionmaker[AsyncSession],
    checker: ModelChecker,
    store: LocalArtifactStore,
    run: RunContext,
) -> VerificationResult:
    """Прогнать движок по каждому свойству, сохранить артефакты и свести результаты."""
    try:
        model = BehavioralModel.model_validate(run.document)
    except ValidationError as invalid:
        return VerificationResult(
            status=VerificationStatus.MODEL_INVALID,
            engine=ENGINE_WHEN_NOT_RUN,
            error_detail=f"документ модели не прошёл валидацию: {invalid}",
        )

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
    return combine([outcome.result for outcome in outcomes])


async def _explain(
    ctx: dict[str, Any], run: RunContext, result: VerificationResult
) -> tuple[VerificationResult, VerificationExplanation]:
    """Объяснить нарушение на языке требований либо вернуть честный шаблон.

    LLM вызывается только при ``PROPERTY_VIOLATED``. Для остальных статусов
    сценария не существует: ``PROPERTY_HOLDS`` — это отсутствие нарушений в
    конечной модели, а таймаут и ошибка движка вообще не результат. Отдавать их
    модели на пересказ значило бы дать ей возможность выдать отказ за успех.

    Returns:
        Результат, дополненный ссылками на требования, и объяснение.
    """
    fallback = VerificationExplanation(business_summary=summary_for(result.status))
    client: LLMClient | None = ctx.get(_LLM_KEY)
    if result.status is not VerificationStatus.PROPERTY_VIOLATED or client is None:
        return result, fallback
    if not run.requirement_text:
        logger.warning(
            "у прогона %s нет текста требования: объяснение остаётся шаблонным",
            run.verification_id,
        )
        return result, fallback

    try:
        model = BehavioralModel.model_validate(run.document)
        answered = await explain_result(
            client,
            requirement_text=run.requirement_text,
            model=model,
            result=result,
            attempts=LLMSettings.from_env().max_attempts,
        )
    except (LLMError, ValidationError) as error:
        logger.warning("объяснение контрпримера не получено, остаётся шаблон: %s", error)
        return result, fallback
    enriched = result.model_copy(update={"related_requirements": answered.related_requirements})
    return enriched, answered.explanation


async def startup(ctx: dict[str, Any]) -> None:
    """Подключение к брокеру и подготовка адаптеров."""
    engine, sessionmaker = create_engine_and_sessionmaker()
    ctx["db_engine"] = engine
    ctx[_SESSIONS_KEY] = sessionmaker
    ctx[_ENGINE_KEY] = ModelChecker(EngineSettings.from_env())
    ctx[_STORE_KEY] = LocalArtifactStore.from_env()
    ctx[_LLM_KEY] = client_from_env() if LLMSettings.from_env().is_configured else None
    ctx["started"] = True


async def shutdown(ctx: dict[str, Any]) -> None:
    """Аккуратное завершение: отпустить соединения перед остановкой процесса."""
    client: LLMClient | None = ctx.pop(_LLM_KEY, None)
    if client is not None:
        await client.aclose()
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
