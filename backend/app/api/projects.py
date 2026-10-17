import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database.models import Project, Requirement, User
from app.db import get_session
from app.errors import FORBIDDEN, NOT_FOUND, ApiError
from app.repositories import projects

router = APIRouter(tags=["projects"])


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class RequirementIn(BaseModel):
    raw_text: str = Field(min_length=1)


class ProjectOut(BaseModel):
    id: str
    name: str
    description: str | None
    created_at: str
    updated_at: str


class RequirementOut(BaseModel):
    id: str
    project_id: str
    version: int
    raw_text: str
    is_current: bool
    created_at: str


def _project_out(project: Project) -> ProjectOut:
    return ProjectOut(
        id=str(project.id),
        name=project.name,
        description=project.description,
        created_at=project.created_at.isoformat(),
        updated_at=project.updated_at.isoformat(),
    )


def _requirement_out(requirement: Requirement) -> RequirementOut:
    return RequirementOut(
        id=str(requirement.id),
        project_id=str(requirement.project_id),
        version=requirement.version,
        raw_text=requirement.raw_text,
        is_current=requirement.is_current,
        created_at=requirement.created_at.isoformat(),
    )


async def _owned_project(session: AsyncSession, project_id: uuid.UUID, user: User) -> Project:
    """Проект с проверкой владельца.

    Отсутствие проекта и чужой проект различаются: ``id`` чужого проекта известен клиенту,
    скрывать существование не требуется.
    """
    await _assert_project_exists(session, project_id)
    project = await projects.get_for_owner(session, project_id, user.id)
    if project is None:
        raise ApiError(403, FORBIDDEN, "Проект принадлежит другому пользователю")
    return project


async def _assert_project_exists(session: AsyncSession, project_id: uuid.UUID) -> None:
    statement = select(Project.id).where(Project.id == project_id)
    if await session.scalar(statement) is None:
        raise ApiError(404, NOT_FOUND, "Проект не найден")


@router.get("/projects")
async def list_projects(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, list[ProjectOut]]:
    """Проекты текущего пользователя."""
    owned = await projects.list_for_owner(session, user.id)
    return {"items": [_project_out(item) for item in owned]}


@router.post("/projects", status_code=status.HTTP_201_CREATED, response_model=ProjectOut)
async def create_project(
    payload: ProjectIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> ProjectOut:
    """Создать проект от имени текущего пользователя."""
    created = await projects.create(
        session,
        owner_id=user.id,
        name=payload.name,
        description=payload.description,
    )
    return _project_out(created)


@router.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> ProjectOut:
    """Проект по id: чужой — 403, несуществующий — 404."""
    return _project_out(await _owned_project(session, project_id, user))


@router.patch("/projects/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> ProjectOut:
    """Переименовать проект и тронуть updated_at."""
    await _assert_project_exists(session, project_id)
    updated = await projects.update(
        session,
        project_id,
        user.id,
        name=payload.name,
        description=payload.description,
    )
    if updated is None:
        raise ApiError(403, FORBIDDEN, "Проект принадлежит другому пользователю")
    return _project_out(updated)


@router.get("/projects/{project_id}/requirements")
async def list_requirements(
    project_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, list[RequirementOut]]:
    """Версии требований по убыванию номера."""
    await _owned_project(session, project_id, user)
    listed = await projects.list_requirements(session, project_id, user.id)
    return {"items": [_requirement_out(item) for item in listed]}


@router.post(
    "/projects/{project_id}/requirements",
    status_code=status.HTTP_201_CREATED,
    response_model=RequirementOut,
)
async def add_requirement(
    project_id: uuid.UUID,
    payload: RequirementIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> RequirementOut:
    """Новая версия, а не правка прежней: текст первой версии остаётся неизменным."""
    await _owned_project(session, project_id, user)
    created = await projects.add_requirement_version(
        session, project_id, raw_text=payload.raw_text, created_by=user.id
    )
    if created is None:
        raise ApiError(404, NOT_FOUND, "Проект не найден")
    return _requirement_out(created)


@router.get("/requirements/{requirement_id}", response_model=RequirementOut)
async def get_requirement(
    requirement_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> RequirementOut:
    """Версия требования по id."""
    requirement = await projects.get_requirement_for_owner(session, requirement_id, user.id)
    if requirement is not None:
        return _requirement_out(requirement)
    await _assert_requirement_exists(session, requirement_id)
    raise ApiError(403, FORBIDDEN, "Требование принадлежит другому пользователю")


async def _assert_requirement_exists(session: AsyncSession, requirement_id: uuid.UUID) -> None:
    statement = select(Requirement.id).where(Requirement.id == requirement_id)
    if await session.scalar(statement) is None:
        raise ApiError(404, NOT_FOUND, "Требование не найдено")
