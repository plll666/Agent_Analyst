import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Project, Requirement


async def create(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    name: str,
    description: str | None = None,
) -> Project:
    """Создать проект. Владелец известен на момент создания и не меняется."""
    now = datetime.now().astimezone()
    project = Project(
        id=uuid.uuid4(),
        owner_id=owner_id,
        name=name,
        description=description,
        created_at=now,
        updated_at=now,
    )
    session.add(project)
    await session.flush()
    return project


async def list_for_owner(session: AsyncSession, owner_id: uuid.UUID) -> list[Project]:
    """Проекты владельца, свежие сверху: так фронт рисует список без пересортировки."""
    statement = (
        select(Project)
        .where(Project.owner_id == owner_id)
        .order_by(Project.updated_at.desc(), Project.name.asc())
    )
    return list(await session.scalars(statement))


async def get_for_owner(
    session: AsyncSession, project_id: uuid.UUID, owner_id: uuid.UUID
) -> Project | None:
    """Проект по id и владельцу. ``None`` означает и «нет», и «чужой» — наружу это 404."""
    statement = select(Project).where(Project.id == project_id, Project.owner_id == owner_id)
    return await session.scalar(statement)


async def update(
    session: AsyncSession,
    project_id: uuid.UUID,
    owner_id: uuid.UUID,
    *,
    name: str,
    description: str | None,
) -> Project | None:
    """Обновить имя и описание, тронув ``updated_at``."""
    project = await get_for_owner(session, project_id, owner_id)
    if project is None:
        return None
    project.name = name
    project.description = description
    project.updated_at = datetime.now().astimezone()
    await session.flush()
    return project


async def delete(session: AsyncSession, project_id: uuid.UUID, owner_id: uuid.UUID) -> bool:
    """Удалить проект вместе с требованиями, моделями и прогонами."""
    project = await get_for_owner(session, project_id, owner_id)
    if project is None:
        return False
    await session.delete(project)
    await session.flush()
    return True


async def add_requirement_version(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    raw_text: str,
    created_by: uuid.UUID | None = None,
) -> Requirement | None:
    """Добавить версию требования и сделать её текущей.

    Строка проекта блокируется: уникального индекса на ``(project_id, version)`` нет,
    поэтому без блокировки два параллельных вызова выдали бы одну версию. ``created_by``
    заполняет система, владение по нему не проверяется.
    """
    locked = await session.scalar(select(Project).where(Project.id == project_id).with_for_update())
    if locked is None:
        return None

    current = await session.scalar(
        select(func.max(Requirement.version)).where(Requirement.project_id == project_id)
    )
    next_version = (current or 0) + 1

    await session.execute(
        sql_update(Requirement)
        .where(Requirement.project_id == project_id, Requirement.is_current.is_(True))
        .values(is_current=False)
    )
    requirement = Requirement(
        id=uuid.uuid4(),
        project_id=project_id,
        version=next_version,
        raw_text=raw_text,
        is_current=True,
        created_by=created_by,
        created_at=datetime.now().astimezone(),
    )
    session.add(requirement)
    await session.flush()
    return requirement


async def list_requirements(
    session: AsyncSession, project_id: uuid.UUID, owner_id: uuid.UUID
) -> list[Requirement]:
    """Версии по убыванию номера: таймлайн рисуется без пересортировки."""
    statement = (
        select(Requirement)
        .join(Project, Project.id == Requirement.project_id)
        .where(Requirement.project_id == project_id, Project.owner_id == owner_id)
        .order_by(Requirement.version.desc())
    )
    return list(await session.scalars(statement))


async def get_requirement_for_owner(
    session: AsyncSession, requirement_id: uuid.UUID, owner_id: uuid.UUID
) -> Requirement | None:
    """Версия требования по id и владельцу проекта."""
    statement = (
        select(Requirement)
        .join(Project, Project.id == Requirement.project_id)
        .where(Requirement.id == requirement_id, Project.owner_id == owner_id)
    )
    return await session.scalar(statement)
