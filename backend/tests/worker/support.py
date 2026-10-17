"""Общие данные и приспособления тестов воркера.

Вынесены из ``conftest.py`` в отдельный модуль: ``conftest.py`` не импортируется
по имени, а фикстуры и вспомогательные функции используются в нескольких файлах
тестов.
"""

import os
import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.models import Artifact, ModelVersion, Verification
from app.database.session import session_scope
from app.domain.behavioral_model import BehavioralModel
from tests.domain.case_examples import case_model, fixed_model

JAR = Path(os.getenv("TLA_TOOLS_JAR", "/opt/tla/tla2tools.jar"))

requires_java = pytest.mark.skipif(
    not JAR.is_file(),
    reason=f"нужен tla2tools.jar: задайте TLA_TOOLS_JAR (сейчас ищем {JAR})",
)


class SeededRun:
    """Идентификаторы созданной цепочки строк."""

    def __init__(self) -> None:
        self.owner_id = uuid.uuid4()
        self.project_id = uuid.uuid4()
        self.model_version_id = uuid.uuid4()
        self.verification_id = uuid.uuid4()


async def seed_store_document(
    sessions: async_sessionmaker[AsyncSession], model_version_id: uuid.UUID, document: Any
) -> None:
    """Положить документ модели в ту версию, на которую ссылается прогон.

    Args:
        sessions: Фабрика сессий.
        model_version_id: Версия модели прогона.
        document: Документ, уже прошедший доменную валидацию.
    """
    async with session_scope(sessions) as session:
        version = await session.get(ModelVersion, model_version_id)
        assert version is not None
        version.document = validated(document)


async def seed_raw_document(
    sessions: async_sessionmaker[AsyncSession], model_version_id: uuid.UUID, document: Any
) -> None:
    """Положить документ без доменной валидации.

    Нужно ровно для одного сценария: модель в базе оказалась невалидной и фоновая
    задача обязана это распознать. Через :func:`seed_store_document` такой документ
    не дошёл бы до проверки.
    """
    async with session_scope(sessions) as session:
        version = await session.get(ModelVersion, model_version_id)
        assert version is not None
        version.document = document


async def fetch_verification(
    sessions: async_sessionmaker[AsyncSession], verification_id: uuid.UUID
) -> Verification | None:
    """Прочитать строку прогона после записи."""
    async with session_scope(sessions) as session:
        return await session.get(Verification, verification_id)


async def fetch_artifact_kinds(
    sessions: async_sessionmaker[AsyncSession], verification_id: uuid.UUID
) -> list[str]:
    """Виды артефактов, сохранённых для прогона."""
    async with session_scope(sessions) as session:
        rows = await session.execute(
            select(Artifact.kind).where(Artifact.verification_id == verification_id)
        )
        return sorted(rows.scalars().all())


def validated(document: Any) -> Any:
    """Документ, прогнанный через доменную валидацию.

    Так тесты не расходятся с доменом: фикстура, которую домен отверг, падает
    здесь, а не внутри движка как ``MODEL_INVALID`` — иначе тест движка проверял бы
    домен.
    """
    return BehavioralModel.model_validate(document).model_dump(mode="json")


def acceptance_model(fixed: bool) -> dict[str, Any]:
    """Модель приёмки из кейса: одно свойство ``forbidden_state`` поверх тех же переходов.

    Приёмочные тесты кейса — про конкретное требование «отменённую заявку нельзя
    исполнять», а не про все четыре свойства общей модели сразу. Поэтому из общей
    модели берётся только это свойство, и тест проверяет ровно то, о чём сказано в
    кейсе.

    Args:
        fixed: Вторая версия модели — ``Cancel`` сбрасывает ``approved``.

    Returns:
        Документ модели с одним свойством приёмки.
    """
    document = fixed_model() if fixed else case_model()
    document["properties"] = [
        prop for prop in document["properties"] if prop["type"] == "forbidden_state"
    ]
    return document
