"""Фоновые задачи arq: проверка модели, объяснение и запись результата.

Задача получает идентификатор строки ``verifications``, а не саму модель: модель
читается из БД по ``model_version_id``, поэтому воркер работает ровно с тем
документом, который агент положил в базу, и не может проверить другую версию.

Движок и агент остаются разными компонентами: ``ModelChecker`` не знает про LLM,
а объяснение вызывается уже после того, как статус получен. Если LLM недоступна,
результат движка всё равно записывается с честным шаблонным текстом — проверка не
должна пропадать из-за провайдера.

Каждая задача идемпотентна и защищена finalizer'ом:

* ``job_id`` равен идентификатору прогона, поэтому потерянный прогон можно
  перевставить без дублей;
* задача тянет прогон только в статусе ``PENDING`` — повтор постановки после
  сбое не запускает работу заново;
* неожиданное исключение или снятие задачи по ``job_timeout`` записывает
  ``ENGINE_ERROR`` в строку прогона, а не молча завершает задачу;
* свип-цикл переводит в ``ENGINE_ERROR`` строки, которые задача не обработала.
"""

import asyncio
import contextlib
import logging
import os
import uuid
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any

from arq.connections import RedisSettings
from arq.jobs import Job, JobStatus
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agent.explainer import explain_result
from app.agent.llm import LLMClient, LLMError, LLMSettings, client_from_env
from app.agent.orchestrator import (
    ENGINE_WHEN_AGENT_FAILED,
    CycleLimits,
    run_iteration,
)
from app.database.models import Verification
from app.database.session import create_engine_and_sessionmaker, session_scope
from app.domain.behavioral_model import BehavioralModel, Property
from app.domain.explanation import summary_for
from app.domain.verdict import combine
from app.domain.verification import (
    VerificationExplanation,
    VerificationResult,
    VerificationStatus,
)
from app.repositories import runs
from app.worker.artifacts import LocalArtifactStore, RunArtifacts, StoredArtifact
from app.worker.model_checker import EngineSettings, ModelChecker
from app.worker.repository import (
    AnalysisContext,
    RunContext,
    VerificationNotFoundError,
    attach_model_version,
    load_analysis_context,
    load_run_context,
    save_artifact_rows,
    save_model_version,
    save_result,
)

# Без этого INFO-логи приложения (вызовы LLM, версии промптов, токены) теряются:
# arq настраивает только свои логгеры, а корень остаётся на WARNING.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

# Внутри Compose переменная задана (redis://redis:6379/0), локальный запуск
# по умолчанию ходит на localhost — как и в docker compose сервиса redis.
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
ENGINE_WHEN_NOT_RUN = "TLC"
ENGINE_WHEN_CRASHED = "NONE"
MAX_REBUILDS = 2

_ENGINE_KEY = "model_checker"
_STORE_KEY = "artifact_store"
_SESSIONS_KEY = "db_sessionmaker"
_LLM_KEY = "llm_client"
_SWEEP_TASK_KEY = "pending_sweep_task"

_SWEEP_INTERVAL_SECONDS = 30.0
# Свежий прогон не трогаем: постановка задачи ещё в полёте после коммита.
_SWEEP_MIN_AGE_SECONDS = 45.0
# Граница перевода «зависшего» прогона в ENGINE_ERROR. Должна превышать
# job_timeout (900 с): честно живая задача длинной LLM-итерации умирает в
# arq раньше, поэтому порог берём с запасом.
_SWEEP_DEADLINE_SECONDS = 2 * 900.0


class CheckBehaviorError(RuntimeError):
    """Проверку выполнить нельзя и записать результат некуда.

    Отдельный тип нужен, чтобы arq пометил задачу как упавшую: молчаливый выход
    оставил бы строку в ``PENDING`` навсегда, и фронт опрашивал бы её до
    бесконечности.
    """


async def ping(_ctx: dict[str, Any]) -> str:
    """Проверка живости очереди: задача доходит до воркера и возвращает результат."""
    return "pong"


async def run_analysis(
    ctx: dict[str, Any], verification_id: str, reasoning: bool | None = None
) -> str:
    """Провести итерацию агента: построить модель, проверить, объяснить, записать.

    Итерация целиком живёт в воркере: HTTP-запрос отвечает сразу, а агент
    работает в фоне. Модель сохраняется сразу после ворот — пользователь видит
    её, пока движок ещё перебирает состояния.

    Задача защищена finalizer'ом. Неожиданное исключение или снятие по
    ``job_timeout`` записывает ``ENGINE_ERROR`` в строку прогона, поэтому
    «вечно ожидающих» строк не остаётся. После обычного исключения задача
    перезапускается arq: идемпотентная проверка статуса запрещает работу
    повторно.

    Args:
        ctx: Контекст arq с адаптерами, подготовленными в :func:`startup`.
        verification_id: Идентификатор строки ``verifications``.
        reasoning: Рассуждать ли модели до ответа; ``None`` — умолчание провайдера.

    Returns:
        Терминальный статус строкой.

    Raises:
        CheckBehaviorError: если строки прогона нет либо сохранить результат не
            удалось.
    """
    identifier = uuid.UUID(verification_id)
    sessions = ctx[_SESSIONS_KEY]
    try:
        return await _run_agent_iteration(ctx, identifier, reasoning)
    except (asyncio.CancelledError, TimeoutError):
        # arq ждёт нас по job_timeout, снятие по рестарту прерывает работу
        # в произвольной точке — результат должен появиться в БД.
        await _finalize_crashed(
            sessions,
            identifier,
            "итерация прервана: снята по job_timeout или при остановке воркера",
        )
        raise
    except Exception as error:
        # В строке прогона — честный отказ, а не висящее PENDING: воркер
        # обязан описать, что упало, иначе фронт показывал бы «идёт анализ».
        await _finalize_crashed(sessions, identifier, f"итерация упала: {error!r}")
        raise


async def _run_agent_iteration(
    ctx: dict[str, Any], identifier: uuid.UUID, reasoning: bool | None
) -> str:
    """Тело задачи :func:`run_analysis` без finalizer'а."""
    sessionmaker = ctx[_SESSIONS_KEY]
    checker: ModelChecker = ctx[_ENGINE_KEY]
    store: LocalArtifactStore = ctx[_STORE_KEY]
    client: LLMClient | None = ctx.get(_LLM_KEY)

    await _check_run_is_pending(sessionmaker, identifier)

    try:
        context = await load_analysis_context(sessionmaker, identifier)
    except VerificationNotFoundError as missing:
        raise CheckBehaviorError(str(missing)) from missing

    if client is None:
        return await _fail_without_llm(sessionmaker, context)
    if not context.requirement_text:
        return await _fail_without_llm(
            sessionmaker, context, "у проекта нет текста требования: строить модель не из чего"
        )

    # Ключ — путь файла: при перестройке модели свойство проверяется повторно,
    # и последняя версия артефактов должна заменить предыдущую, а не задвоиться.
    artifacts: dict[str, StoredArtifact] = {}

    async def check_property(model: BehavioralModel, prop: Property) -> VerificationResult:
        outcome = await checker.check(model, prop)
        for stored in store.save_run(
            str(context.verification_id),
            [
                RunArtifacts(
                    property_id=prop.id,
                    spec=outcome.spec.tla,
                    cfg=outcome.spec.cfg,
                    output=outcome.output,
                )
            ],
        ):
            artifacts[stored.storage_uri] = stored
        return outcome.result

    async def on_model(model: BehavioralModel) -> None:
        nonlocal context
        version_id = await save_model_version(sessionmaker, context, model)
        await attach_model_version(sessionmaker, context.verification_id, version_id)
        context = replace(context, model_version_id=version_id)

    settings = LLMSettings.from_env()
    iteration = await run_iteration(
        client=client,
        requirement_text=context.requirement_text,
        check_property=check_property,
        limits=CycleLimits(
            build_attempts=settings.max_attempts,
            max_rebuilds=MAX_REBUILDS,
            explanation_attempts=settings.max_attempts,
        ),
        on_model=on_model,
        reasoning=reasoning,
    )

    if artifacts:
        await save_artifact_rows(sessionmaker, context, list(artifacts.values()))
    if iteration.result is not None:
        await save_result(sessionmaker, context, iteration.result, iteration.explanation)

    logger.info(
        "итерация %s: статус %s, решение %s, перестроений %s, замечаний %s, рассуждения %s",
        identifier,
        iteration.status,
        iteration.decision,
        iteration.rebuilds,
        len(iteration.gate_problems),
        reasoning,
    )
    return str(iteration.status)


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
    identifier = uuid.UUID(verification_id)
    sessions = ctx[_SESSIONS_KEY]
    try:
        return await _check_and_save(ctx, identifier)
    except CheckBehaviorError:
        raise
    except (asyncio.CancelledError, TimeoutError):
        await _finalize_crashed(
            sessions,
            identifier,
            "проверка прервана: снята по job_timeout или при остановке воркера",
        )
        raise
    except Exception as error:
        await _finalize_crashed(sessions, identifier, f"проверка упала: {error!r}")
        raise


async def _check_and_save(ctx: dict[str, Any], identifier: uuid.UUID) -> str:
    """Тело задачи :func:`check_behavior` без finalizer'а."""
    sessionmaker = ctx[_SESSIONS_KEY]
    checker: ModelChecker = ctx[_ENGINE_KEY]
    store: LocalArtifactStore = ctx[_STORE_KEY]

    await _check_run_is_pending(sessionmaker, identifier)

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
        identifier,
        result.status,
        result.property_id,
    )
    return str(result.status)


async def _check_run_is_pending(
    sessionmaker: async_sessionmaker[AsyncSession], verification_id: uuid.UUID
) -> None:
    """Отказаться от прогона, который уже не находится в статусе ``PENDING``.

    Задача становится идемпотентной: повторная постановка после сбоя или свип
    не запускает работу для прогона, у которого результат уже записан.

    Raises:
        CheckBehaviorError: если строки прогона нет — сохранять результат некуда.
    """
    async with session_scope(sessionmaker) as session:
        row = await session.get(Verification, verification_id)
        if row is None:
            raise CheckBehaviorError(f"прогон {verification_id} не найден")
        if row.status != VerificationStatus.PENDING:
            logger.info("прогон %s пропущен: статус %s уже записан", verification_id, row.status)
            raise CheckBehaviorError(f"прогон {verification_id} уже завершён статусом {row.status}")


async def _finalize_crashed(
    sessionmaker: async_sessionmaker[AsyncSession], verification_id: uuid.UUID, detail: str
) -> None:
    """Записать отказ упавшей задачи под защитой щита.

    Отмена задачи не должна отменить запись: результат должен быть честным и для
    прогона, снятого по ``job_timeout``. Запись защищена :func:`asyncio.shield`,
    а её неудача не скрывается — свип всё равно догонит строку по дедлайнуу.

    Args:
        sessionmaker: Фабрика сессий воркера.
        verification_id: Идентификатор строки ``verifications``.
        detail: Причина отказа — попадает в ``error_detail`` и лог.
    """

    async def write() -> None:
        async with session_scope(sessionmaker) as session:
            await runs.save_result(
                session,
                verification_id,
                status=str(VerificationStatus.ENGINE_ERROR),
                engine=ENGINE_WHEN_CRASHED,
                business_summary=summary_for(VerificationStatus.ENGINE_ERROR),
                error_detail=detail,
            )

    try:
        await asyncio.wait_for(asyncio.shield(write()), timeout=10.0)
    except Exception as shield_error:  # noqa: BLE001 - запись не должна прервать задачу
        logger.error("прогон %s: не удалось записать отказ в БД: %s", verification_id, shield_error)
    else:
        logger.warning("прогон %s: %s", verification_id, detail)


async def _fail_without_llm(
    sessionmaker: async_sessionmaker[AsyncSession],
    context: AnalysisContext,
    detail: str = "LLM не настроена: не заданы LLM_BASE_URL, LLM_API_KEY или LLM_MODEL",
) -> str:
    """Записать отказ агента, когда провайдер недоступен."""
    result = VerificationResult(
        status=VerificationStatus.AGENT_ERROR,
        engine=ENGINE_WHEN_AGENT_FAILED,
        error_detail=detail,
    )
    explanation = VerificationExplanation(
        business_summary=summary_for(VerificationStatus.AGENT_ERROR)
    )
    await save_result(sessionmaker, context, result, explanation)
    logger.warning("итерация %s: %s", context.verification_id, detail)
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


async def _sweep_pending(ctx: dict[str, Any]) -> int:
    """Перевставить потерянные прогоны и остановить «вечно ожидаемые».

    Строка прогона в статусе ``PENDING`` — собственный «outbox» задачи: постановка
    в broker не входит в транзакцию записи, поэтому постановка может потеряться
    между коммитом и ``enqueue_job``. Свип восстанавливает такие прогоны: задача
    перевставляется по ``job_id``, и повторов не бывает — arq не заводит дубль
    для существующего идентификатора, а идемпотентный обработчик отказывается
    повторять завершённый прогон.

    Returns:
        Сколько прогонов потребовали вмешательства: перевставлены или завершены.
    """
    pool = ctx.get("redis")
    if pool is None:
        return 0
    sessions: async_sessionmaker[AsyncSession] = ctx[_SESSIONS_KEY]

    # Прогоны без активной задачи: их можно перевставить или закрыть.
    handled = 0
    horizon = datetime.now().astimezone() - timedelta(seconds=_SWEEP_MIN_AGE_SECONDS)
    for row in await _pending_rows(sessions, horizon):
        job_id = str(row.id)
        job_status = await _job_status(pool, job_id)
        if job_status in (JobStatus.queued, JobStatus.in_progress, JobStatus.deferred):
            continue

        age = (datetime.now().astimezone() - row.created_at).total_seconds()
        if age > _SWEEP_DEADLINE_SECONDS:
            handled += await _finalize_stale(sessions, row)
            continue

        if await _push(pool, row):
            handled += 1
            logger.info("прогон %s перевставлен: задача прогона %s", job_id, job_status)

    return handled


async def _pending_rows(
    sessionmaker: async_sessionmaker[AsyncSession], older_than: datetime
) -> list[Verification]:
    """Прогоны ``PENDING`` не старше «свежих»: постановка ещё могла не быть выполнена."""
    async with session_scope(sessionmaker) as session:
        statement = select(Verification).where(
            Verification.status == VerificationStatus.PENDING,
            Verification.created_at <= older_than,
        )
        return list((await session.scalars(statement)).all())


async def _job_status(pool: Any, job_id: str) -> JobStatus | None:
    """Статус задачи по ``job_id``; недоступный broker не останавливает свип."""
    try:
        return await Job(job_id=job_id, redis=pool).status()
    except Exception as error:  # noqa: BLE001 - redis недоступен, надо ждать
        logger.warning("не удалось опросить задачу %s: %s", job_id, error)
        return None


async def _push(pool: Any, row: Verification) -> bool:
    """Перевставить задачу прогона: агентная для строк без модели, движковая — с.

    Returns:
        ``True``, если arq создал новую задачу; ``False`` — задача уже стоит
        или выполняется, вмешательства не было.
    """
    if row.model_version_id is None:
        job = await pool.enqueue_job(
            "run_analysis", str(row.id), _job_id=str(row.id), reasoning=row.reasoning
        )
    else:
        job = await pool.enqueue_job("check_behavior", str(row.id), _job_id=str(row.id))
    return job is not None


async def _finalize_stale(
    sessionmaker: async_sessionmaker[AsyncSession], row: Verification
) -> bool:
    """Закрыть «вечно ожидаемый» прогон как ENGINE_ERROR.

    Свип не перезаписывает терминальный статус: задача могла завершиться
    между выборкой и записью, — проверяется ``WHERE status = 'PENDING'``.

    Returns:
        ``True``, если прогон закрыт; ``False`` — он уже завершился сам.
    """
    detail = (
        f"задача не завершилась за {int(_SWEEP_DEADLINE_SECONDS)} с: воркер не записал результат"
    )
    async with session_scope(sessionmaker) as session:
        pending = await session.scalar(
            select(Verification.id).where(
                Verification.id == row.id,
                Verification.status == VerificationStatus.PENDING,
            )
        )
        if pending is None:
            logger.info("прогон %s уже завершён, свип не трогает", row.id)
            return False
        await runs.save_result(
            session,
            row.id,
            status=str(VerificationStatus.ENGINE_ERROR),
            engine=ENGINE_WHEN_CRASHED,
            business_summary=summary_for(VerificationStatus.ENGINE_ERROR),
            error_detail=detail,
        )
    logger.warning("прогон %s закрыт свипом: %s", row.id, detail)
    return True


async def _sweep_loop(ctx: dict[str, Any]) -> None:
    """Периодическое восстановление прогонов: переводит строки из «PENDING»."""
    while True:
        try:
            await asyncio.sleep(_SWEEP_INTERVAL_SECONDS)
            await _sweep_pending(ctx)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 - свип не должен падать
            logger.warning("свип PENDING не выполнен: %s", error)


async def startup(ctx: dict[str, Any]) -> None:
    """Подключение к брокеру и подготовка адаптеров.

    Свип запускается фоново и перевставляет потерянные прогоны: его период и
    дедлайн зависят от ``job_timeout``, а не от типа задачи.
    """
    engine, sessionmaker = create_engine_and_sessionmaker()
    ctx["db_engine"] = engine
    ctx[_SESSIONS_KEY] = sessionmaker
    ctx[_ENGINE_KEY] = ModelChecker(EngineSettings.from_env())
    ctx[_STORE_KEY] = LocalArtifactStore.from_env()
    ctx[_LLM_KEY] = client_from_env() if LLMSettings.from_env().is_configured else None
    ctx[_SWEEP_TASK_KEY] = asyncio.create_task(_sweep_loop(ctx))
    ctx["started"] = True


async def shutdown(ctx: dict[str, Any]) -> None:
    """Аккуратное завершение: отпустить соединения и остановить свип перед остановкой."""
    sweep: asyncio.Task[None] | None = ctx.pop(_SWEEP_TASK_KEY, None)
    if sweep is not None and not sweep.done():
        sweep.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sweep
    client: LLMClient | None = ctx.pop(_LLM_KEY, None)
    if client is not None:
        await client.aclose()
    engine: AsyncEngine | None = ctx.pop("db_engine", None)
    if engine is not None:
        await engine.dispose()
    ctx["started"] = False


class WorkerSettings:
    """Настройки arq. Загружаются командой `arq app.worker.main.WorkerSettings`."""

    functions: list[Any] = [ping, run_analysis, check_behavior]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(REDIS_URL)
    max_jobs = 1
    job_timeout = 900
