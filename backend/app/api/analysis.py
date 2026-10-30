import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, StringConstraints, ValidationError
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
from app.database.models import ModelVersion, Requirement, User
from app.database.models import Verification as VerificationRecord
from app.db import get_session
from app.domain.behavioral_model import BehavioralModel
from app.domain.verification import RootCause
from app.errors import LLM_UNAVAILABLE, NOT_FOUND, VALIDATION_ERROR, ApiError
from app.queue import enqueue_analysis, enqueue_check
from app.repositories import projects as projects_repo
from app.repositories import runs
from app.repositories.runs import verification_to_domain
from app.services import model_build

router = APIRouter(tags=["analysis"])

ENGINE_WHEN_RUN = "TLC"


class ModelBuildIn(BaseModel):
    requirement_id: uuid.UUID | None = None


class AnalysisStartIn(BaseModel):
    requirement_id: uuid.UUID | None = None
    reasoning: bool | None = None


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
        }
    )
    return payload


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
    return {"items": [_verification_out(record) for record in listed]}


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
        session, project_id=project_id, model_version_id=latest.id, engine=ENGINE_WHEN_RUN
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
    _assert_llm_configured()

    await _assert_reasoning_supported(payload.reasoning)
    pending = await runs.create_pending_verification(
        session,
        project_id=project_id,
        model_version_id=None,
        engine=ENGINE_WHEN_RUN,
        # Требование фиксируется при запуске: воркер обязан проверить именно
        # выбранный текст, а не тот, что станет «текущим», пока задача ждёт.
        requirement_id=requirement.id,
        reasoning=payload.reasoning,
    )
    await session.commit()
    await enqueue_analysis(str(pending.id), reasoning=payload.reasoning)
    await session.refresh(pending)
    return _verification_out(pending)


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
    current = await projects_repo.current_requirement(session, project_id)
    if current is None:
        raise ApiError(422, VALIDATION_ERROR, "Сначала сохраните текст требования")
    _assert_llm_configured()

    clarified = await projects_repo.add_requirement_version(
        session,
        project_id,
        raw_text=f"{current.raw_text}\n\nУточнение пользователя: {payload.answer}",
        created_by=user.id,
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
