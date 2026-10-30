"""Доступ воркера к PostgreSQL: прочитать модель прогона и записать результат.

Отдельный модуль, а не функции в ``main.py``: у ``main.py`` оркестрация очереди,
а здесь только чтение и запись. Запись полей прогона делегируется общему
репозиторию ``app.repositories.runs``: две реализации одной записи разъехались бы
по набору полей, и объяснение агента терялось бы на одном из путей.

Все значения приходят из доменных типов и раскладываются по колонкам явно.
Значения по умолчанию вида ``result.get("status", "ENGINE_ERROR")`` здесь
запрещены: они превращали бы любую забытую колонку в «движок не смог проверить»,
а пользователь увидел бы отказ без причины.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.models import Artifact, ModelVersion, Requirement, Verification
from app.database.session import session_scope
from app.domain.behavioral_model import BehavioralModel, schema_hash
from app.domain.verification import (
    RelatedRequirement,
    VerificationExplanation,
    VerificationResult,
)
from app.repositories import runs
from app.worker.artifacts import StoredArtifact


class VerificationNotFoundError(LookupError):
    """Прогона с таким идентификатором нет.

    Отдельный тип нужен, чтобы вызывающая сторона отличила «задача устарела» от
    «проверка провалилась»: первое — ошибка постановки в очередь, второе —
    результат, который пишется в БД.
    """


@dataclass(frozen=True, slots=True)
class RunContext:
    """Всё, что фоновой задаче нужно знать о прогоне до запуска движка."""

    verification_id: uuid.UUID
    project_id: uuid.UUID
    model_version_id: uuid.UUID
    document: dict[str, Any]
    requirement_text: str | None


@dataclass(frozen=True, slots=True)
class AnalysisContext:
    """Всё, что итерации агента нужно знать до её начала.

    В отличие от :class:`RunContext` модели тут ещё нет: её строит агент, и
    только после этого прогон получает версию модели.
    """

    verification_id: uuid.UUID
    project_id: uuid.UUID
    requirement_id: uuid.UUID | None
    requirement_text: str | None
    model_version_id: uuid.UUID | None
    parent_model_version_id: uuid.UUID | None


RunLike = RunContext | AnalysisContext


async def load_analysis_context(
    sessionmaker: async_sessionmaker[AsyncSession], verification_id: uuid.UUID
) -> AnalysisContext:
    """Прочитать проект прогона, зафиксированное требование и предыдущую модель.

    Текст берётся из версии требования, на которую прогон ссылается: требование
    зафиксировано в момент запуска, и очередь не может подменить вход задачи.
    Фолбэк на «текущую» версию остаётся только для старых прогонов, созданных до
    миграции 0006, — у них ссылки нет и восстановить её достоверно нельзя.
    Предыдущая версия модели нужна как родитель новой — из неё получается
    цепочка итераций.

    Args:
        sessionmaker: Фабрика сессий воркера.
        verification_id: Идентификатор строки ``verifications``.

    Returns:
        Контекст итерации.

    Raises:
        VerificationNotFoundError: если строки прогона нет.
    """
    async with session_scope(sessionmaker) as session:
        record = await session.get(Verification, verification_id)
        if record is None:
            raise VerificationNotFoundError(f"прогон {verification_id} не найден")
        requirement = await _requirement(session, record.project_id, record.requirement_id)
        parent = await session.scalar(
            select(ModelVersion.id)
            .where(ModelVersion.project_id == record.project_id)
            .order_by(ModelVersion.version.desc())
            .limit(1)
        )
    return AnalysisContext(
        verification_id=record.id,
        project_id=record.project_id,
        requirement_id=requirement.id if requirement is not None else None,
        requirement_text=requirement.raw_text if requirement is not None else None,
        model_version_id=record.model_version_id,
        parent_model_version_id=parent,
    )


async def _requirement(
    session: AsyncSession, project_id: uuid.UUID, requirement_id: uuid.UUID | None
) -> Requirement | None:
    """Требование прогона: выбранное при запуске или, для старых строк, текущее."""
    if requirement_id is not None:
        return await session.get(Requirement, requirement_id)
    return await _current_requirement(session, project_id)


async def save_model_version(
    sessionmaker: async_sessionmaker[AsyncSession],
    context: AnalysisContext,
    model: BehavioralModel,
) -> uuid.UUID:
    """Сохранить построенную агентом модель и вернуть её идентификатор.

    Args:
        sessionmaker: Фабрика сессий воркера.
        context: Контекст итерации.
        model: Модель, прошедшая ворота.

    Returns:
        Идентификатор сохранённой версии модели.

    Raises:
        VerificationNotFoundError: если проект исчез.
    """
    document = model.model_dump(mode="json")
    async with session_scope(sessionmaker) as session:
        record = await runs.create_next_model_version(
            session,
            context.project_id,
            source="agent",
            document=document,
            schema_hash=schema_hash(document),
            validation_status="VALID",
            requirement_id=context.requirement_id,
            parent_version_id=context.parent_model_version_id,
        )
        if record is None:
            raise VerificationNotFoundError(f"проект {context.project_id} не найден")
        return record.id


async def attach_model_version(
    sessionmaker: async_sessionmaker[AsyncSession],
    verification_id: uuid.UUID,
    model_version_id: uuid.UUID,
) -> None:
    """Привязать прогон к построенной модели.

    Args:
        sessionmaker: Фабрика сессий воркера.
        verification_id: Идентификатор строки ``verifications``.
        model_version_id: Идентификатор версии модели.

    Raises:
        VerificationNotFoundError: если строки прогона нет.
    """
    async with session_scope(sessionmaker) as session:
        record = await session.get(Verification, verification_id)
        if record is None:
            raise VerificationNotFoundError(f"прогон {verification_id} не найден")
        record.model_version_id = model_version_id


async def load_run_context(
    sessionmaker: async_sessionmaker[AsyncSession], verification_id: uuid.UUID
) -> RunContext:
    """Прочитать строку прогона вместе с документом модели и текстом требования.

    Текст берётся из версии требования, по которой построена модель. Если связи
    нет (модель создана до миграции 0003), используется текущая версия проекта:
    объяснить контрпример без исходного текста нельзя, а молча оставить пустую
    строку — значит скрыть, что объяснения не будет.

    Args:
        sessionmaker: Фабрика сессий воркера.
        verification_id: Идентификатор строки ``verifications``.

    Returns:
        Контекст прогона.

    Raises:
        VerificationNotFoundError: если строки нет — сохранять результат некуда, и
            молча выйти означало бы потерять задачу.
    """
    async with session_scope(sessionmaker) as session:
        row = (
            await session.execute(
                select(Verification, ModelVersion.document, ModelVersion.requirement_id)
                .join(ModelVersion, Verification.model_version_id == ModelVersion.id)
                .where(Verification.id == verification_id)
            )
        ).first()
        if row is None:
            raise VerificationNotFoundError(f"прогон {verification_id} не найден")
        verification, document, requirement_id = row
        requirement = await _requirement_text(session, verification.project_id, requirement_id)
    return RunContext(
        verification_id=verification.id,
        project_id=verification.project_id,
        model_version_id=verification.model_version_id,
        document=document,
        requirement_text=requirement,
    )


async def _requirement_text(
    session: AsyncSession, project_id: uuid.UUID, requirement_id: uuid.UUID | None
) -> str | None:
    """Текст требования, по которому строилась модель."""
    if requirement_id is not None:
        linked = await session.get(Requirement, requirement_id)
        return linked.raw_text if linked is not None else None
    current = await _current_requirement(session, project_id)
    return current.raw_text if current is not None else None


async def _current_requirement(session: AsyncSession, project_id: uuid.UUID) -> Requirement | None:
    """Текущая версия требования проекта."""
    return await session.scalar(
        select(Requirement).where(
            Requirement.project_id == project_id, Requirement.is_current.is_(True)
        )
    )


async def save_result(
    sessionmaker: async_sessionmaker[AsyncSession],
    run: RunLike,
    result: VerificationResult,
    explanation: VerificationExplanation,
) -> None:
    """Записать результат проверки и объяснение агента в строку ``verifications``.

    Пишутся и поля движка, и объяснение, потому что объяснение без результата
    бессмысленно, а результат без объяснения нарушает контракт: у терминального
    прогона ``business_summary`` не может быть пустым.

    Args:
        sessionmaker: Фабрика сессий воркера.
        run: Контекст прогона из :func:`load_run_context`.
        result: Результат проверки от движка.
        explanation: Объяснение агента либо шаблонный текст, если LLM недоступна.

    Raises:
        VerificationNotFoundError: если строка прогона исчезла.
    """
    async with session_scope(sessionmaker) as session:
        saved = await runs.save_result(
            session,
            run.verification_id,
            status=str(result.status),
            engine=result.engine,
            business_summary=explanation.business_summary,
            property_id=result.property_id,
            engine_version=result.engine_version,
            statistics=_jsonable(result.statistics),
            counterexample=_jsonable(result.counterexample),
            related_requirements=_related_json(result.related_requirements),
            duration_ms=result.duration_ms,
            error_detail=result.error_detail,
            hypothesis=explanation.hypothesis,
            question=explanation.question,
            root_cause=str(explanation.root_cause) if explanation.root_cause else None,
        )
    if saved is None:
        raise VerificationNotFoundError(f"прогон {run.verification_id} не найден")


async def save_artifact_rows(
    sessionmaker: async_sessionmaker[AsyncSession],
    run: RunLike,
    artifacts: list[StoredArtifact],
) -> None:
    """Связать сохранённые файлы с прогоном.

    Без этих строк ссылку на ``.tla`` и ``.cfg`` некуда записать, а прогон нельзя
    будет воспроизвести вручную: по контракту API на экране анализа доступны
    артефакты прогона.

    Args:
        sessionmaker: Фабрика сессий воркера.
        run: Контекст прогона из :func:`load_run_context`.
        artifacts: Метаданные файлов, уже сохранённых на диск.
    """
    async with session_scope(sessionmaker) as session:
        session.add_all(
            [
                Artifact(
                    id=uuid.uuid4(),
                    project_id=run.project_id,
                    model_version_id=run.model_version_id,
                    verification_id=run.verification_id,
                    kind=artifact.kind,
                    storage_uri=artifact.storage_uri,
                    sha256=artifact.sha256,
                    size_bytes=artifact.size_bytes,
                )
                for artifact in artifacts
            ]
        )


def _related_json(
    requirements: tuple[RelatedRequirement, ...] | None,
) -> list[dict[str, Any]] | None:
    """Разложить ссылки на требования по элементам JSONB."""
    if requirements is None:
        return None
    return [requirement.model_dump(mode="json") for requirement in requirements]


def _jsonable(value: Any) -> Any:
    """Привести доменный объект к тому, что понимает JSONB.

    ``model_dump(mode="json")`` вместо ``dict()``: у полей разные типы на входе и на
    выходе, а JSONB различает ``str`` и ``bool`` и хранит их по-разному.

    Args:
        value: Доменный объект либо ``None``.

    Returns:
        Сериализуемое значение либо ``None``.
    """
    if value is None:
        return None
    return value.model_dump(mode="json")
