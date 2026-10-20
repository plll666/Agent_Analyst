import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Artifact, ModelVersion, Project, Verification
from app.domain.verification import (
    Counterexample,
    RelatedRequirement,
    RootCause,
    Statistics,
    VerificationExplanation,
    VerificationResult,
    VerificationStatus,
)
from app.domain.verification import (
    Verification as DomainVerification,
)


async def create_model_version(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    version: int,
    source: str,
    document: dict[str, Any],
    schema_hash: str,
    validation_status: str,
    validation_errors: list[str] | None = None,
    parent_version_id: uuid.UUID | None = None,
    requirement_id: uuid.UUID | None = None,
    created_by: uuid.UUID | None = None,
) -> ModelVersion:
    """Сохранить интерпретацию агента как объект."""
    record = ModelVersion(
        id=uuid.uuid4(),
        project_id=project_id,
        parent_version_id=parent_version_id,
        requirement_id=requirement_id,
        version=version,
        source=source,
        document=document,
        schema_hash=schema_hash,
        validation_status=validation_status,
        validation_errors=validation_errors or [],
        created_by=created_by,
        created_at=datetime.now().astimezone(),
    )
    session.add(record)
    await session.flush()
    return record


async def create_next_model_version(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    source: str,
    document: dict[str, Any],
    schema_hash: str,
    validation_status: str,
    validation_errors: list[str] | None = None,
    requirement_id: uuid.UUID | None = None,
    parent_version_id: uuid.UUID | None = None,
    created_by: uuid.UUID | None = None,
) -> ModelVersion | None:
    """Создать следующую версию модели, заблокировав проект.

    Без блокировки два параллельных запроса прочитали бы один и тот же максимум и
    выдали две версии с одинаковым номером: уникального индекса на
    ``(project_id, version)`` нет.

    Args:
        session: Открытая сессия.
        project_id: Проект, к которому относится модель.
        source: ``agent`` или ``manual``.
        document: Проверенный документ модели.
        schema_hash: Хэш документа.
        validation_status: ``VALID`` или ``INVALID``.
        validation_errors: Список нарушений для невалидной модели.
        requirement_id: Версия требования, по которой построена модель.
        parent_version_id: Предыдущая версия при уточнении.
        created_by: Автор версии.

    Returns:
        Созданная версия либо ``None``, если проекта нет.
    """
    locked = await session.scalar(
        select(Project.id).where(Project.id == project_id).with_for_update()
    )
    if locked is None:
        return None
    current = await session.scalar(
        select(func.max(ModelVersion.version)).where(ModelVersion.project_id == project_id)
    )
    return await create_model_version(
        session,
        project_id,
        version=(current or 0) + 1,
        source=source,
        document=document,
        schema_hash=schema_hash,
        validation_status=validation_status,
        validation_errors=validation_errors,
        requirement_id=requirement_id,
        parent_version_id=parent_version_id,
        created_by=created_by,
    )


async def latest_model_version(
    session: AsyncSession, project_id: uuid.UUID, owner_id: uuid.UUID
) -> ModelVersion | None:
    """Последняя версия модели проекта."""
    statement = (
        select(ModelVersion)
        .join(Project, Project.id == ModelVersion.project_id)
        .where(ModelVersion.project_id == project_id, Project.owner_id == owner_id)
        .order_by(ModelVersion.version.desc())
        .limit(1)
    )
    return await session.scalar(statement)


async def list_models_for_owner(
    session: AsyncSession, project_id: uuid.UUID, owner_id: uuid.UUID
) -> list[ModelVersion]:
    """Версии модели по убыванию."""
    statement = (
        select(ModelVersion)
        .join(Project, Project.id == ModelVersion.project_id)
        .where(ModelVersion.project_id == project_id, Project.owner_id == owner_id)
        .order_by(ModelVersion.version.desc())
    )
    return list(await session.scalars(statement))


async def create_pending_verification(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    model_version_id: uuid.UUID | None,
    engine: str,
) -> Verification:
    """Завести прогон в статусе ``PENDING``; ``business_summary`` пока пуст.

    ``model_version_id`` может быть пустым: в агентном цикле прогон заводится до
    того, как модель построена, — её строит агент внутри задачи.
    """
    record = Verification(
        id=uuid.uuid4(),
        project_id=project_id,
        model_version_id=model_version_id,
        status="PENDING",
        engine=engine,
        business_summary="",
        created_at=datetime.now().astimezone(),
    )
    session.add(record)
    await session.flush()
    return record


async def list_verifications(
    session: AsyncSession, project_id: uuid.UUID, owner_id: uuid.UUID
) -> list[Verification]:
    """Прогоны проекта, новые сверху."""
    statement = (
        select(Verification)
        .join(Project, Project.id == Verification.project_id)
        .where(Verification.project_id == project_id, Project.owner_id == owner_id)
        .order_by(Verification.created_at.desc())
    )
    return list(await session.scalars(statement))


async def get_verification_for_owner(
    session: AsyncSession, verification_id: uuid.UUID, owner_id: uuid.UUID
) -> Verification | None:
    """Прогон по id и владельцу проекта."""
    statement = (
        select(Verification)
        .join(Project, Project.id == Verification.project_id)
        .where(Verification.id == verification_id, Project.owner_id == owner_id)
    )
    return await session.scalar(statement)


async def get_verification(
    session: AsyncSession, verification_id: uuid.UUID
) -> Verification | None:
    """Прогон без проверки владельца: вызывается воркером, у которого её нет."""
    return await session.get(Verification, verification_id)


async def save_result(
    session: AsyncSession,
    verification_id: uuid.UUID,
    *,
    status: str,
    engine: str,
    business_summary: str,
    property_id: str | None = None,
    engine_version: str | None = None,
    statistics: dict[str, Any] | None = None,
    counterexample: dict[str, Any] | None = None,
    related_requirements: list[dict[str, Any]] | None = None,
    duration_ms: int | None = None,
    error_detail: str | None = None,
    hypothesis: str | None = None,
    question: str | None = None,
    root_cause: str | None = None,
) -> Verification | None:
    """Записать результат проверки в строку прогона."""
    record = await get_verification(session, verification_id)
    if record is None:
        return None

    record.status = status
    record.engine = engine
    record.property_id = property_id
    record.engine_version = engine_version
    record.statistics = statistics
    record.counterexample = counterexample
    record.related_requirements = related_requirements
    record.duration_ms = duration_ms
    record.error_detail = error_detail
    record.business_summary = business_summary
    record.hypothesis = hypothesis
    record.question = question
    record.root_cause = root_cause

    await session.flush()
    return record


async def create_artifact(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    kind: str,
    storage_uri: str,
    sha256: str,
    size_bytes: int,
    model_version_id: uuid.UUID | None = None,
    verification_id: uuid.UUID | None = None,
) -> Artifact:
    """Привязать артефакт прогона: ``.tla``, ``.cfg`` или трассу."""
    record = Artifact(
        id=uuid.uuid4(),
        project_id=project_id,
        model_version_id=model_version_id,
        verification_id=verification_id,
        kind=kind,
        storage_uri=storage_uri,
        sha256=sha256,
        size_bytes=size_bytes,
        created_at=datetime.now().astimezone(),
    )
    session.add(record)
    await session.flush()
    return record


def verification_to_domain(record: Verification) -> DomainVerification:
    """Собрать доменный агрегат из строки прогона."""
    result = VerificationResult(
        status=VerificationStatus(record.status),
        property_id=record.property_id,
        engine=record.engine,
        engine_version=record.engine_version,
        statistics=Statistics.model_validate(record.statistics) if record.statistics else None,
        counterexample=(
            Counterexample.model_validate(record.counterexample) if record.counterexample else None
        ),
        related_requirements=(
            tuple(RelatedRequirement.model_validate(item) for item in record.related_requirements)
            if record.related_requirements
            else None
        ),
        duration_ms=record.duration_ms,
        error_detail=record.error_detail,
    )
    explanation = VerificationExplanation(
        business_summary=record.business_summary,
        hypothesis=record.hypothesis,
        question=record.question,
        root_cause=RootCause(record.root_cause) if record.root_cause else None,
    )
    return DomainVerification(result=result, explanation=explanation)
