"""Доступ воркера к PostgreSQL: прочитать модель прогона и записать результат.

Отдельный модуль, а не функции в ``main.py``: у ``main.py`` оркестрация очереди,
а здесь только чтение и запись. Это проверяется не тестом на структуру файла, а
возможностью прогнать запись без arq.

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

from app.database.models import Artifact, ModelVersion, Verification
from app.database.session import session_scope
from app.domain.verification import VerificationResult
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


async def load_run_context(
    sessionmaker: async_sessionmaker[AsyncSession], verification_id: uuid.UUID
) -> RunContext:
    """Прочитать строку прогона вместе с документом модели.

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
                select(Verification, ModelVersion.document)
                .join(ModelVersion, Verification.model_version_id == ModelVersion.id)
                .where(Verification.id == verification_id)
            )
        ).first()
    if row is None:
        raise VerificationNotFoundError(f"прогон {verification_id} не найден")
    verification, document = row
    return RunContext(
        verification_id=verification.id,
        project_id=verification.project_id,
        model_version_id=verification.model_version_id,
        document=document,
    )


async def save_result(
    sessionmaker: async_sessionmaker[AsyncSession],
    run: RunContext,
    result: VerificationResult,
    business_summary: str,
) -> None:
    """Записать результат проверки в строку ``verifications``.

    Пишутся только поля движка. ``business_summary`` передаётся отдельно, потому
    что его наполняет агент, а не модель-чекер; запись без него оставила бы
    терминальный прогон с пустым объяснением, а это прямо запрещено контрактом.

    Args:
        sessionmaker: Фабрика сессий воркера.
        run: Контекст прогона из :func:`load_run_context`.
        result: Результат проверки от движка.
        business_summary: Текст, который пользователь увидит вместо сценария.

    Raises:
        VerificationNotFoundError: если строка прогона исчезла.
    """
    async with session_scope(sessionmaker) as session:
        verification = await session.get(Verification, run.verification_id, with_for_update=True)
        if verification is None:
            raise VerificationNotFoundError(f"прогон {run.verification_id} не найден")
        verification.status = str(result.status)
        verification.property_id = result.property_id
        verification.engine = result.engine
        verification.engine_version = result.engine_version
        verification.statistics = _jsonable(result.statistics)
        verification.counterexample = _jsonable(result.counterexample)
        verification.related_requirements = _jsonable(result.related_requirements)
        verification.duration_ms = result.duration_ms
        verification.error_detail = result.error_detail
        verification.business_summary = business_summary


async def save_artifact_rows(
    sessionmaker: async_sessionmaker[AsyncSession],
    run: RunContext,
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
