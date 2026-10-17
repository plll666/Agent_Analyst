from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import UserOut, _to_out
from app.auth import get_current_user
from app.database.models import Project, Requirement, User, Verification
from app.db import get_session

router = APIRouter(prefix="/users", tags=["profile"])


class ProfileSummaryOut(BaseModel):
    user: UserOut
    projects_count: int
    requirement_versions_count: int
    verification_count: int
    violation_count: int
    last_verification_at: str | None


@router.get("/me/summary", response_model=ProfileSummaryOut)
async def summary(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> ProfileSummaryOut:
    """Один агрегирующий запрос вместо N+1: счётчики требуют обхода всех проектов."""
    projects_count = await session.scalar(
        select(func.count()).select_from(Project).where(Project.owner_id == user.id)
    )
    versions_count = await session.scalar(
        select(func.count())
        .select_from(Requirement)
        .join(Project, Project.id == Requirement.project_id)
        .where(Project.owner_id == user.id)
    )
    runs_count = await session.scalar(
        select(func.count())
        .select_from(Verification)
        .join(Project, Project.id == Verification.project_id)
        .where(Project.owner_id == user.id)
    )
    violations_count = await session.scalar(
        select(func.count())
        .select_from(Verification)
        .join(Project, Project.id == Verification.project_id)
        .where(Project.owner_id == user.id, Verification.status == "PROPERTY_VIOLATED")
    )
    last_run = await session.scalar(
        select(func.max(Verification.created_at))
        .select_from(Verification)
        .join(Project, Project.id == Verification.project_id)
        .where(Project.owner_id == user.id)
    )
    return ProfileSummaryOut(
        user=_to_out(user),
        projects_count=projects_count or 0,
        requirement_versions_count=versions_count or 0,
        verification_count=runs_count or 0,
        violation_count=violations_count or 0,
        last_verification_at=last_run.isoformat() if last_run else None,
    )
