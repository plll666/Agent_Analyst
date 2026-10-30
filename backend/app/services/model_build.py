"""Построение версии модели из текста требования.

Сервис связывает агента (LLM), домен (валидация модели) и репозиторий (запись
версии). Модель не правится после проверки: здесь создаётся только новая версия,
и только по явному запросу пользователя.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm import LLMClient
from app.agent.modeler import build_model
from app.database.models import ModelVersion, Requirement
from app.domain.behavioral_model import schema_hash
from app.repositories import runs


class ProjectNotFoundError(LookupError):
    """Проекта нет: версию модели не к чему привязать."""


async def build_model_version(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    requirement: Requirement,
    client: LLMClient,
    attempts: int,
    created_by: uuid.UUID,
) -> ModelVersion:
    """Построить и сохранить новую версию модели.

    Args:
        session: Открытая сессия.
        project_id: Проект, в котором создаётся версия.
        requirement: Версия требования — источник текста и связь для объяснения.
        client: Клиент LLM.
        attempts: Сколько попыток дать агенту на валидный документ.
        created_by: Автор версии.

    Returns:
        Сохранённая версия модели.

    Raises:
        ProjectNotFoundError: проект исчез между проверкой прав и записью.
        LLMResponseError: агент не смог построить валидную модель.
        LLMError: провайдер недоступен.
    """
    model = await build_model(client, requirement_text=requirement.raw_text, attempts=attempts)
    document = model.model_dump(mode="json")
    record = await runs.create_next_model_version(
        session,
        project_id,
        source="agent",
        document=document,
        schema_hash=schema_hash(document),
        validation_status="VALID",
        requirement_id=requirement.id,
        created_by=created_by,
    )
    if record is None:
        raise ProjectNotFoundError(f"проект {project_id} не найден")
    return record
