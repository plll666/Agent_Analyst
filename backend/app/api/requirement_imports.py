"""Импорт требования с предпросмотром до подтверждения."""

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.projects import _owned_project
from app.auth import get_current_user
from app.config import get_settings
from app.database.models import RequirementImport, User
from app.db import get_session
from app.domain.importing import FILE_TOO_LARGE, ImportFailure, detect_format, extract
from app.errors import NOT_FOUND, ApiError

router = APIRouter(tags=["requirement-imports"])


def _out(record: RequirementImport) -> dict:
    return {
        "id": str(record.id),
        "project_id": str(record.project_id),
        "filename": record.filename,
        "format": record.format,
        "size_bytes": record.size_bytes,
        "sha256": record.sha256,
        "raw_text": record.raw_text,
        "fragments": record.fragments,
        "warnings": record.warnings,
        "created_at": record.created_at.isoformat(),
    }


async def _get(
    session: AsyncSession, project_id: uuid.UUID, import_id: uuid.UUID
) -> RequirementImport:
    record = await session.get(RequirementImport, import_id)
    if record is None or record.project_id != project_id:
        raise ApiError(404, NOT_FOUND, "Импорт не найден в этом проекте")
    return record


@router.get("/projects/{project_id}/requirement-imports/capabilities")
async def capabilities(
    project_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Вернуть фактические ограничения импорта для проекта."""
    await _owned_project(session, project_id, user)
    settings = get_settings()
    return {
        "formats": ["txt", "docx"],
        "max_file_bytes": settings.import_max_file_bytes,
        "max_text_chars": settings.import_max_text_chars,
        "txt_encoding": settings.import_txt_encoding,
    }


@router.post("/projects/{project_id}/requirement-imports", status_code=201)
async def upload_import(
    project_id: uuid.UUID,
    file: Annotated[UploadFile, File()],
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Извлечь текст файла и сохранить предпросмотр."""
    await _owned_project(session, project_id, user)
    settings = get_settings()
    filename = Path(file.filename or "").name
    try:
        file_format = detect_format(filename)
        data = await file.read(settings.import_max_file_bytes + 1)
        if len(data) > settings.import_max_file_bytes:
            raise ImportFailure(FILE_TOO_LARGE, "Файл превышает допустимый размер")
        extracted = extract(
            file_format,
            data,
            max_text_chars=settings.import_max_text_chars,
            max_unpacked_bytes=settings.import_max_unpacked_bytes,
            max_archive_entries=settings.import_max_archive_entries,
        )
    except ImportFailure as error:
        code = (
            413
            if error.code == FILE_TOO_LARGE
            else 415
            if error.code == "UNSUPPORTED_FILE_TYPE"
            else 422
        )
        raise ApiError(code, error.code, error.message) from error

    import_id = uuid.uuid4()
    storage_dir = await asyncio.to_thread(Path(settings.import_storage_dir).resolve)
    await asyncio.to_thread(storage_dir.mkdir, parents=True, exist_ok=True)
    path = storage_dir / str(import_id)
    await asyncio.to_thread(path.write_bytes, data)
    record = RequirementImport(
        id=import_id,
        project_id=project_id,
        filename=filename,
        format=file_format,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        raw_text=extracted.raw_text,
        fragments=[fragment.model_dump() for fragment in extracted.fragments],
        warnings=[warning.model_dump() for warning in extracted.warnings],
        storage_uri=str(path),
        created_by=user.id,
        created_at=datetime.now(UTC),
    )
    session.add(record)
    try:
        await session.commit()
    except Exception:
        await asyncio.to_thread(path.unlink, missing_ok=True)
        raise
    return _out(record)


@router.get("/projects/{project_id}/requirement-imports/{import_id}")
async def get_import(
    project_id: uuid.UUID,
    import_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Получить сохранённый предпросмотр импорта."""
    await _owned_project(session, project_id, user)
    return _out(await _get(session, project_id, import_id))


@router.get("/projects/{project_id}/requirement-imports/{import_id}/file")
async def get_file(
    project_id: uuid.UUID,
    import_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> FileResponse:
    """Скачать исходный файл владельцу проекта."""
    await _owned_project(session, project_id, user)
    record = await _get(session, project_id, import_id)
    path = Path(record.storage_uri)
    if not await asyncio.to_thread(path.is_file):
        raise ApiError(404, NOT_FOUND, "Исходный файл не найден")
    return FileResponse(path, filename=record.filename, media_type="application/octet-stream")
