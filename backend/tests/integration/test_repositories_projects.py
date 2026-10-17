"""Репозитории против настоящего Postgres.

Без поднятой БД тесты пропускаются: слой доступа к данным не проверить заглушкой —
заглушка проверит саму себя.
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import projects, users

pytestmark = pytest.mark.integration


def _email(name: str) -> str:
    """Уникальный адрес на прогон: тесты делят одну базу между запусками."""
    return f"{name}-{uuid.uuid4().hex}@example.com"


async def test_creates_user(session: AsyncSession) -> None:
    user = await users.create(session, email=_email("anna"), password_hash="hash")

    assert user.id is not None
    assert user.is_active is True
    assert user.last_login_at is None


async def test_finds_user_by_email_ignoring_case(session: AsyncSession) -> None:
    email = _email("anna")
    await users.create(session, email=email, password_hash="hash")

    found = await users.get_by_email_lower(session, email.upper())

    assert found is not None
    assert found.email == email


async def test_email_busy_in_any_case(session: AsyncSession) -> None:
    email = _email("bob")
    await users.create(session, email=email, password_hash="hash")

    with pytest.raises(Exception, match="duplicate key"):
        await users.create(session, email=email.upper(), password_hash="hash")


async def test_unknown_email_returns_none(session: AsyncSession) -> None:
    assert await users.get_by_email_lower(session, _email("nobody")) is None


async def test_touch_last_login(session: AsyncSession) -> None:
    user = await users.create(session, email=_email("carol"), password_hash="hash")

    await users.touch_last_login(session, user.id)
    await session.commit()
    await session.refresh(user)

    assert user.last_login_at is not None


async def test_creates_project(session: AsyncSession, owner_id: uuid.UUID) -> None:
    project = await projects.create(
        session, owner_id=owner_id, name="Модуль заявок", description="создание заявки"
    )

    assert project.owner_id == owner_id
    assert project.description == "создание заявки"


async def test_lists_only_own_projects(
    session: AsyncSession, owner_id: uuid.UUID, stranger_id: uuid.UUID
) -> None:
    await projects.create(session, owner_id=owner_id, name="Мой проект")
    await projects.create(session, owner_id=stranger_id, name="Чужой проект")

    visible = await projects.list_for_owner(session, owner_id)

    assert [item.name for item in visible] == ["Мой проект"]


async def test_foreign_project_is_invisible(
    session: AsyncSession, owner_id: uuid.UUID, stranger_id: uuid.UUID
) -> None:
    created = await projects.create(session, owner_id=stranger_id, name="Чужой проект")

    assert await projects.get_for_owner(session, created.id, owner_id) is None
    assert await projects.get_for_owner(session, created.id, stranger_id) is not None


async def test_update_and_delete_require_owner(
    session: AsyncSession, owner_id: uuid.UUID, stranger_id: uuid.UUID
) -> None:
    created = await projects.create(session, owner_id=owner_id, name="Проект")

    assert (
        await projects.update(session, created.id, stranger_id, name="Взлом", description=None)
        is None
    )
    assert await projects.delete(session, created.id, stranger_id) is False

    updated = await projects.update(
        session, created.id, owner_id, name="Переименован", description="новое"
    )
    assert updated is not None
    assert updated.name == "Переименован"


async def test_update_touches_updated_at(session: AsyncSession, owner_id: uuid.UUID) -> None:
    created = await projects.create(session, owner_id=owner_id, name="Проект")
    before = created.updated_at

    updated = await projects.update(session, created.id, owner_id, name="Другое", description=None)

    assert updated is not None
    assert updated.updated_at >= before
