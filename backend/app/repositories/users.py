import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User


async def create(
    session: AsyncSession,
    *,
    email: str,
    password_hash: str,
    display_name: str | None = None,
) -> User:
    """Создать пользователя. Уникальность email держит индекс ``ix_users_email_lower``."""
    user = User(
        id=uuid.uuid4(),
        email=email,
        password_hash=password_hash,
        display_name=display_name,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user


async def get_by_email_lower(session: AsyncSession, email: str) -> User | None:
    """Найти по email без учёта регистра: занятость в любом написании."""
    statement = select(User).where(func.lower(User.email) == email.strip().lower())
    return await session.scalar(statement)


async def get_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    """Найти по идентификатору."""
    return await session.get(User, user_id)


async def touch_last_login(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Проставить время последнего входа, не читая объект целиком."""
    await session.execute(
        update(User).where(User.id == user_id).values(last_login_at=datetime.now().astimezone())
    )
