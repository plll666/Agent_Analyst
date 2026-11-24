import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, StringConstraints, ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.capabilities import detect_reasoning
from app.agent.llm import (
    LLMConfigurationError,
    LLMError,
    LLMFactory,
    LLMResponseError,
    LLMSettings,
    client_from_env,
)
from app.api.projects import _owned_project
from app.auth import get_current_user
from app.config import get_settings
from app.database.models import ModelVersion, Requirement, User, VerificationEvent
from app.database.models import Verification as VerificationRecord
from app.db import get_session, session_scope
from app.domain.behavioral_model import BehavioralModel
from app.domain.verification import RootCause
from app.errors import LLM_UNAVAILABLE, NOT_FOUND, RUN_ALREADY_FINISHED, VALIDATION_ERROR, ApiError
from app.queue import enqueue_analysis, enqueue_check
from app.repositories import projects as projects_repo
from app.repositories import runs
from app.repositories.runs import verification_to_domain
from app.services import model_build
from app.services.run_key import (
    analysis_config_snapshot,
    analysis_input_key,
    model_check_config_snapshot,
    model_check_input_key,
)

router = APIRouter(tags=["analysis"])

ENGINE_WHEN_RUN = "TLC"


class ModelBuildIn(BaseModel):
    requirement_id: uuid.UUID | None = None


class AnalysisStartIn(BaseModel):
    requirement_id: uuid.UUID | None = None
    reasoning: bool | None = None
    force_recompute: bool = False


class AnalysisAnswerIn(BaseModel):
    answer: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ModelVersionOut(BaseModel):
    id: str
    project_id: str
    version: int
    source: str
    requirement_id: str | None = None
    parent_version_id: str | None = None
    schema_hash: str
    validation_status: str
    validation_errors: list[str]
    document: dict[str, Any]
    created_at: str


def _model_out(record: ModelVersion) -> ModelVersionOut:
    return ModelVersionOut(
        id=str(record.id),
        project_id=str(record.project_id),
        version=record.version,
        source=record.source,
        requirement_id=str(record.requirement_id) if record.requirement_id else None,
        parent_version_id=str(record.parent_version_id) if record.parent_version_id else None,
        schema_hash=record.schema_hash,
        validation_status=record.validation_status,
        validation_errors=list(record.validation_errors or []),
        document=record.document,
        created_at=record.created_at.isoformat(),
    )


def _verification_out(record: VerificationRecord) -> dict[str, Any]:
    """Плоский ресурс прогона: домен уже свёрнут, остаётся идентичность записи."""
    payload = verification_to_domain(record).model_dump(mode="json")
    payload.update(
        {
            "id": str(record.id),
            "project_id": str(record.project_id),
            "model_version_id": (str(record.model_version_id) if record.model_version_id else None),
            "requirement_id": (str(record.requirement_id) if record.requirement_id else None),
            "reasoning": record.reasoning,
            "created_at": record.created_at.isoformat(),
            "execution_status": record.execution_status,
            "input_key": record.input_key,
            "run_config": record.run_config,
            "started_at": record.started_at.isoformat() if record.started_at else None,
            "finished_at": record.finished_at.isoformat() if record.finished_at else None,
            "last_event_seq": record.last_event_seq,
            "active_stages": [],
        }
    )
    return payload


async def _active_stages(session: AsyncSession, record: VerificationRecord) -> list[dict[str, Any]]:
    if record.execution_status in {"COMPLETED", "FAILED", "CANCELLED"}:
        return []
    events = list(
        await session.scalars(
            select(VerificationEvent)
            .where(
                VerificationEvent.verification_id == record.id,
                VerificationEvent.stage_id.is_not(None),
            )
            .order_by(VerificationEvent.seq.desc())
        )
    )
    latest: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.stage_id not in latest and "stage" in event.data:
            latest[event.stage_id] = event.data["stage"]
    return [stage for stage in latest.values() if stage.get("state") == "RUNNING"]


@router.get("/projects/{project_id}/models")
async def list_models(
    project_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, list[ModelVersionOut]]:
    """Версии модели проекта по убыванию."""
    await _owned_project(session, project_id, user)
    listed = await runs.list_models_for_owner(session, project_id, user.id)
    return {"items": [_model_out(item) for item in listed]}


@router.get("/projects/{project_id}/verifications")
async def list_verifications(
    project_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, list[dict[str, Any]]]:
    """Прогоны проекта, новые сверху."""
    await _owned_project(session, project_id, user)
    listed = await runs.list_verifications(session, project_id, user.id)
    items = []
    for record in listed:
        item = _verification_out(record)
        item["active_stages"] = await _active_stages(session, record)
        items.append(item)
    return {"items": items}


async def _owned_run(
    session: AsyncSession, project_id: uuid.UUID, verification_id: uuid.UUID, user: User
) -> VerificationRecord:
    await _owned_project(session, project_id, user)
    record = await runs.get_verification_for_owner(session, verification_id, user.id)
    if record is None or record.project_id != project_id:
        raise ApiError(404, NOT_FOUND, "Прогон не найден в этом проекте")
    return record


@router.get("/projects/{project_id}/verifications/{verification_id}")
async def get_verification(
    project_id: uuid.UUID,
    verification_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """Получить полный ресурс прогона владельца проекта."""
    record = await _owned_run(session, project_id, verification_id, user)
    item = _verification_out(record)
    item["active_stages"] = await _active_stages(session, record)
    return item


@router.get("/projects/{project_id}/verifications/{verification_id}/events")
async def list_events(
    project_id: uuid.UUID,
    verification_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    after_seq: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    """Вернуть сохранённые события после курсора."""
    await _owned_run(session, project_id, verification_id, user)
    if after_seq < 0 or not 1 <= limit <= 500:
        raise ApiError(422, VALIDATION_ERROR, "Неверный курсор или размер страницы")
    rows = list(
        await session.scalars(
            select(VerificationEvent)
            .where(
                VerificationEvent.verification_id == verification_id,
                VerificationEvent.seq > after_seq,
            )
            .order_by(VerificationEvent.seq)
            .limit(limit + 1)
        )
    )
    items = [
        {
            "schema_version": 1,
            "verification_id": str(verification_id),
            "seq": row.seq,
            "occurred_at": row.occurred_at.isoformat(),
            "type": row.type,
            "data": row.data,
        }
        for row in rows[:limit]
    ]
    return {
        "items": items,
        "next_after_seq": items[-1]["seq"] if items else after_seq,
        "has_more": len(rows) > limit,
    }


@router.get("/projects/{project_id}/verifications/{verification_id}/events/stream")
async def stream_events(
    project_id: uuid.UUID,
    verification_id: uuid.UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    after_seq: int = 0,
) -> StreamingResponse:
    """Передавать события SSE с возможностью продолжения после курсора."""
    await _owned_run(session, project_id, verification_id, user)
    last_id = request.headers.get("last-event-id")
    try:
        cursor = int(last_id) if last_id is not None else after_seq
    except ValueError as error:
        raise ApiError(422, VALIDATION_ERROR, "Неверный курсор событий") from error
    if cursor < 0:
        raise ApiError(422, VALIDATION_ERROR, "Неверный курсор событий")
    await session.commit()

    async def events():
        current = cursor
        last_heartbeat = asyncio.get_running_loop().time()
        while not await request.is_disconnected():
            async with session_scope() as event_session:
                rows = list(
                    await event_session.scalars(
                        select(VerificationEvent)
                        .where(
                            VerificationEvent.verification_id == verification_id,
                            VerificationEvent.seq > current,
                        )
                        .order_by(VerificationEvent.seq)
                        .limit(500)
                    )
                )
                run_state = await event_session.scalar(
                    select(VerificationRecord.execution_status).where(
                        VerificationRecord.id == verification_id
                    )
                )
            for row in rows:
                current = row.seq
                envelope = {
                    "schema_version": 1,
                    "verification_id": str(verification_id),
                    "seq": row.seq,
                    "occurred_at": row.occurred_at.isoformat(),
                    "type": row.type,
                    "data": row.data,
                }
                data = json.dumps(envelope, ensure_ascii=False)
                yield f"id: {row.seq}\nevent: {row.type}\ndata: {data}\n\n"
            if run_state in {"COMPLETED", "FAILED", "CANCELLED"} and len(rows) < 500:
                break
            now = asyncio.get_running_loop().time()
            if now - last_heartbeat >= 15:
                yield ": heartbeat\n\n"
                last_heartbeat = now
            await asyncio.sleep(0.5)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/projects/{project_id}/analyses/{verification_id}/cancel")
async def cancel_analysis(
    project_id: uuid.UUID,
    verification_id: uuid.UUID,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """Запросить отмену прогона, сохранив атомарный переход состояния."""
    await _owned_run(session, project_id, verification_id, user)
    record = await session.scalar(
        select(VerificationRecord).where(VerificationRecord.id == verification_id).with_for_update()
    )
    if record.execution_status in {"COMPLETED", "FAILED"}:
        raise ApiError(409, RUN_ALREADY_FINISHED, "Прогон уже завершён")
    if record.execution_status == "CANCELLED":
        return _verification_out(record)
    if record.execution_status == "QUEUED":
        record.execution_status = "CANCELLED"
        record.status = "CANCELLED"
        record.business_summary = "Анализ отменён пользователем"
        record.finished_at = datetime.now(UTC)
        event_type = "run.finished"
    else:
        record.execution_status = "CANCELLING"
        response.status_code = 202
        event_type = "run.updated"
    record.last_event_seq += 1
    session.add(
        VerificationEvent(
            id=uuid.uuid4(),
            verification_id=record.id,
            seq=record.last_event_seq,
            type=event_type,
            stage_id=None,
            data={"execution_status": record.execution_status, "status": record.status},
            occurred_at=datetime.now(UTC),
        )
    )
    await session.flush()
    return _verification_out(record)


@router.post(
    "/projects/{project_id}/verifications",
    status_code=status.HTTP_201_CREATED,
)
async def start_verification(
    project_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """Создать прогон в статусе ``PENDING`` и поставить его в очередь.

    Проверку выполняет воркер, а не этот запрос. Очередь пополняется после коммита,
    иначе воркер заберёт задачу раньше, чем строка станет видна другим транзакциям.
    """
    await _owned_project(session, project_id, user)
    latest = await runs.latest_model_version(session, project_id, user.id)
    if latest is None:
        raise ApiError(422, VALIDATION_ERROR, "Модель ещё не построена — проверять нечего")
    if latest.validation_status != "VALID":
        problems = "; ".join(latest.validation_errors or []) or "причина не указана"
        raise ApiError(422, VALIDATION_ERROR, f"Модель не прошла валидацию: {problems}")

    try:
        BehavioralModel.model_validate(latest.document)
    except ValidationError as error:
        raise ApiError(422, VALIDATION_ERROR, f"Модель не прошла валидацию: {error}") from error

    pending = await runs.create_pending_verification(
        session,
        project_id=project_id,
        model_version_id=latest.id,
        engine=ENGINE_WHEN_RUN,
        input_key=model_check_input_key(project_id=project_id, model_version_id=latest.id),
        run_config=model_check_config_snapshot(),
    )
    await session.commit()
    await enqueue_check(str(pending.id))
    await session.refresh(pending)
    return _verification_out(pending)


def get_llm_factory() -> LLMFactory:
    """Вернуть фабрику клиента LLM.

    Зависимость отдаёт функцию, а не клиента: права на проект проверяются до
    создания соединения с провайдером, и чужой проект не должен упираться в 503
    из-за ненастроенной LLM.
    """
    return client_from_env


async def _resolve_requirement(
    session: AsyncSession,
    project_id: uuid.UUID,
    requirement_id: uuid.UUID | None,
    user: User,
) -> Requirement | None:
    """Выбрать версию требования: указанную или текущую.

    Raises:
        ApiError: указанная версия не найдена в этом проекте.
    """
    if requirement_id is None:
        return await projects_repo.current_requirement(session, project_id)
    found = await projects_repo.get_requirement_for_owner(session, requirement_id, user.id)
    if found is None or found.project_id != project_id:
        raise ApiError(404, NOT_FOUND, "Требование не найдено в этом проекте")
    return found


@router.post("/projects/{project_id}/analyses", status_code=status.HTTP_201_CREATED)
async def start_analysis(
    project_id: uuid.UUID,
    payload: AnalysisStartIn,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """Запустить итерацию агента.

    Агент строит модель по тексту требования, проверяет её детерминированным
    движком и объясняет результат. Всё это происходит в фоне: запрос отвечает
    сразу прогоном в статусе ``PENDING``, а результат появляется позже.
    """
    await _owned_project(session, project_id, user)
    requirement = await _resolve_requirement(session, project_id, payload.requirement_id, user)
    if requirement is None:
        raise ApiError(
            422, VALIDATION_ERROR, "Сначала сохраните текст требования: анализировать нечего"
        )
    if len(requirement.raw_text) > get_settings().llm_max_input_chars:
        raise ApiError(422, VALIDATION_ERROR, "Текст превышает лимит входа настроенной LLM")
    _assert_llm_configured()

    await _assert_reasoning_supported(payload.reasoning)
    input_key = analysis_input_key(
        project_id=project_id,
        requirement_id=requirement.id,
        requirement_text=requirement.raw_text,
        reasoning=payload.reasoning,
    )
    if not payload.force_recompute:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": input_key}
        )
        prior = await session.scalars(
            select(VerificationRecord)
            .where(
                VerificationRecord.project_id == project_id,
                VerificationRecord.input_key == input_key,
            )
            .order_by(VerificationRecord.created_at.desc())
        )
        matching = list(prior)
        reusable = next(
            (
                row
                for row in matching
                if row.execution_status == "COMPLETED"
                and row.status in {"PROPERTY_HOLDS", "PROPERTY_VIOLATED"}
                and row.root_cause != "AGENT_ERROR"
            ),
            None,
        )
        active = next(
            (
                row
                for row in matching
                if row.execution_status in {"QUEUED", "RUNNING", "CANCELLING"}
            ),
            None,
        )
        selected = reusable or active
        if selected is not None:
            response.status_code = 200
            mode = "REUSED" if reusable is not None else "IN_PROGRESS"
            result = _verification_out(selected)
            result["submission"] = {
                "mode": mode,
                "input_key": input_key,
                "matched_verification_id": str(selected.id),
            }
            await session.commit()
            return result
    pending = await runs.create_pending_verification(
        session,
        project_id=project_id,
        model_version_id=None,
        engine=ENGINE_WHEN_RUN,
        # Требование фиксируется при запуске: воркер обязан проверить именно
        # выбранный текст, а не тот, что станет «текущим», пока задача ждёт.
        requirement_id=requirement.id,
        reasoning=payload.reasoning,
        input_key=input_key,
        run_config=analysis_config_snapshot(payload.reasoning),
    )
    await session.commit()
    await enqueue_analysis(str(pending.id), reasoning=payload.reasoning)
    await session.refresh(pending)
    result = _verification_out(pending)
    result["submission"] = {
        "mode": "CREATED",
        "input_key": input_key,
        "matched_verification_id": None,
    }
    return result


@router.post(
    "/projects/{project_id}/analyses/{verification_id}/answer",
    status_code=status.HTTP_201_CREATED,
)
async def answer_analysis(
    project_id: uuid.UUID,
    verification_id: uuid.UUID,
    payload: AnalysisAnswerIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """Ответить на вопрос агента и начать следующую итерацию.

    Ответ не правит модель: он дополняет текст требования, и агент строит по
    нему новую версию модели. Прежние версии требования и модели остаются
    на месте — из них и складывается цепочка итераций.
    """
    await _owned_project(session, project_id, user)
    record = await runs.get_verification_for_owner(session, verification_id, user.id)
    if record is None or record.project_id != project_id:
        raise ApiError(404, NOT_FOUND, "Прогон не найден в этом проекте")
    if not record.question:
        raise ApiError(422, VALIDATION_ERROR, "У этого прогона нет вопроса: отвечать не на что")
    if record.root_cause == RootCause.AGENT_ERROR:
        raise ApiError(
            422,
            VALIDATION_ERROR,
            "Объяснение признало ошибку модели: это не вопрос к требованию, отвечать не на что",
        )
    original = (
        await session.get(Requirement, record.requirement_id) if record.requirement_id else None
    )
    if original is None or original.project_id != project_id:
        raise ApiError(422, VALIDATION_ERROR, "Исходная версия требования недоступна")
    clarified_text = f"{original.raw_text}\n\nУточнение пользователя: {payload.answer}"
    if len(clarified_text) > get_settings().llm_max_input_chars:
        raise ApiError(422, VALIDATION_ERROR, "Текст превышает лимит входа настроенной LLM")
    _assert_llm_configured()

    clarified = await projects_repo.add_requirement_version(
        session,
        project_id,
        raw_text=clarified_text,
        created_by=user.id,
        source_import_id=original.source_import_id,
        source_modified=original.source_import_id is not None,
    )
    if clarified is None:
        raise ApiError(404, NOT_FOUND, "Проект не найден")
    pending = await runs.create_pending_verification(
        session,
        project_id=project_id,
        model_version_id=None,
        engine=ENGINE_WHEN_RUN,
        # Прогон ссылается на уточнённый текст, а не на предыдущий.
        requirement_id=clarified.id,
        reasoning=record.reasoning,
        input_key=analysis_input_key(
            project_id=project_id,
            requirement_id=clarified.id,
            requirement_text=clarified.raw_text,
            reasoning=record.reasoning,
        ),
        run_config=analysis_config_snapshot(record.reasoning),
    )
    await session.commit()
    await enqueue_analysis(str(pending.id), reasoning=record.reasoning)
    await session.refresh(pending)
    return _verification_out(pending)


async def _assert_reasoning_supported(reasoning: bool | None) -> None:
    """Не принимать выбор, который провайдер не умеет выполнить.

    Проверка нужна только когда режим выбран явно: без выбора параметр не
    передаётся, и провайдер работает по своему умолчанию. Неизвестный ответ
    пробы (``None``) не блокирует запуск: сеть могла моргнуть, а галочка на
    фронте и так появляется только при подтверждённой поддержке.
    """
    if reasoning is None:
        return
    capability = await detect_reasoning(LLMSettings.from_env())
    if capability.available is False:
        raise ApiError(
            422,
            VALIDATION_ERROR,
            "Модель не поддерживает рассуждения: "
            + (capability.detail or "провайдер не принимает этот режим"),
        )


@router.get("/llm/capabilities")
async def llm_capabilities(
    _: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """Что умеет настроенная модель: сейчас — только режим рассуждений.

    Фронт спрашивает это перед показом галочки, поэтому ответ кешируется в
    процессе и не ходит к провайдеру на каждое открытие страницы.
    """
    settings = LLMSettings.from_env()
    capability = await detect_reasoning(settings)
    return {"model": settings.model, "reasoning": capability.as_dict()}


def _assert_llm_configured() -> None:
    """Проверить, что провайдер настроен, до постановки задачи в очередь."""
    settings = LLMSettings.from_env()
    if not settings.is_configured:
        raise ApiError(
            503,
            LLM_UNAVAILABLE,
            "LLM не настроена: не заданы " + ", ".join(settings.missing()),
        )


@router.post(
    "/projects/{project_id}/models",
    status_code=status.HTTP_201_CREATED,
    response_model=ModelVersionOut,
)
async def build_model(
    project_id: uuid.UUID,
    payload: ModelBuildIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    llm_factory: Annotated[LLMFactory, Depends(get_llm_factory)],
) -> ModelVersionOut:
    """Построить модель по сохранённому тексту требования.

    Модель строит агент, а не этот запрос: здесь проверка прав, выбор версии
    требования и запись результата. Текст требования читается и фиксируется до
    вызова LLM, чтобы не держать транзакцию на время сетевого запроса. Проверка
    модели запускается отдельно через ``POST /projects/{id}/verifications``.
    """
    await _owned_project(session, project_id, user)
    requirement = await _resolve_requirement(session, project_id, payload.requirement_id, user)
    if requirement is None:
        raise ApiError(
            422,
            VALIDATION_ERROR,
            "Сначала сохраните текст требования: строить модель не из чего",
        )
    await session.commit()

    settings = LLMSettings.from_env()
    try:
        client = llm_factory()
    except LLMConfigurationError as error:
        raise ApiError(503, LLM_UNAVAILABLE, str(error)) from error
    try:
        record = await model_build.build_model_version(
            session,
            project_id=project_id,
            requirement=requirement,
            client=client,
            attempts=settings.max_attempts,
            created_by=user.id,
        )
    except model_build.ProjectNotFoundError as error:
        raise ApiError(404, NOT_FOUND, str(error)) from error
    except LLMResponseError as error:
        problems = "; ".join(error.problems)
        raise ApiError(
            422, VALIDATION_ERROR, f"Агент не смог построить модель: {problems}"
        ) from error
    except LLMError as error:
        raise ApiError(503, LLM_UNAVAILABLE, f"LLM недоступна: {error}") from error
    finally:
        await client.aclose()
    return _model_out(record)
