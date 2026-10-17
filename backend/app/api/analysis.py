import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.projects import _owned_project
from app.auth import get_current_user
from app.checker import StubChecker
from app.database.models import ModelVersion, User
from app.db import get_session
from app.domain.behavioral_model import BehavioralModel
from app.domain.verification import Verification
from app.errors import VALIDATION_ERROR, ApiError
from app.repositories import runs
from app.repositories.runs import verification_to_domain

router = APIRouter(tags=["analysis"])


class ModelVersionOut(BaseModel):
    id: str
    project_id: str
    version: int
    source: str
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
        schema_hash=record.schema_hash,
        validation_status=record.validation_status,
        validation_errors=list(record.validation_errors or []),
        document=record.document,
        created_at=record.created_at.isoformat(),
    )


def _verification_out(record: Any, verification: Verification) -> dict[str, Any]:
    """Плоский ресурс: домен уже свёрнут, остаётся добавить идентичность записи."""
    payload = verification.model_dump(mode="json")
    payload.update(
        {
            "id": str(record.id),
            "project_id": str(record.project_id),
            "model_version_id": str(record.model_version_id),
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
    """Версии модели проекта по убыванию: экран берёт первую как текущую."""
    await _owned_project(session, project_id, user)
    listed = await runs.list_models_for_owner(session, project_id, user.id)
    return {"items": [_model_out(item) for item in listed]}


@router.get("/projects/{project_id}/verifications")
async def list_verifications(
    project_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, list[dict[str, Any]]]:
    """Прогоны проекта с актуальными статусами, без кеша."""
    await _owned_project(session, project_id, user)
    listed = await runs.list_verifications(session, project_id, user.id)
    return {
        "items": [_verification_out(record, verification_to_domain(record)) for record in listed]
    }


@router.post(
    "/projects/{project_id}/verifications",
    status_code=status.HTTP_201_CREATED,
)
async def start_verification(
    project_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """Заводит прогон, выполняет проверку и отдаёт терминальный результат.

    Модель читается и валидируется здесь: движок получает ``BehavioralModel``, а не
    произвольный JSON из базы.
    """
    await _owned_project(session, project_id, user)
    latest = await runs.latest_model_version(session, project_id, user.id)
    if latest is None:
        raise ApiError(422, VALIDATION_ERROR, "Модель ещё не построена — проверять нечего")
    if latest.validation_status != "VALID":
        problems = "; ".join(latest.validation_errors or []) or "причина не указана"
        raise ApiError(422, VALIDATION_ERROR, f"Модель не прошла валидацию: {problems}")

    try:
        model = BehavioralModel.model_validate(latest.document)
    except ValidationError as error:
        raise ApiError(422, VALIDATION_ERROR, f"Модель не прошла валидацию: {error}") from error

    pending = await runs.create_pending_verification(
        session, project_id=project_id, model_version_id=latest.id, engine="stub"
    )
    checker = StubChecker()
    result = await checker.check(model, model.properties[0].id)
    explanation = checker.explain()
    await runs.save_result(
        session,
        pending.id,
        status=result.status.value,
        engine=result.engine,
        business_summary=explanation.business_summary,
        hypothesis=explanation.hypothesis,
        question=explanation.question,
        property_id=result.property_id,
        engine_version=result.engine_version,
        statistics=result.statistics.model_dump(mode="json") if result.statistics else None,
        counterexample=(
            result.counterexample.model_dump(mode="json") if result.counterexample else None
        ),
        related_requirements=None,
        duration_ms=result.duration_ms,
        error_detail=result.error_detail,
    )
    await session.refresh(pending)
    return _verification_out(pending, Verification(result=result, explanation=explanation))
