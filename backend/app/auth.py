import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Cookie, Depends, Response
from jwt import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database.models import User
from app.db import get_session
from app.errors import UNAUTHENTICATED, ApiError
from app.repositories import users

SESSION_COOKIE = "session"
MIN_PASSWORD_LENGTH = 8

_hasher = PasswordHasher()

# Хеш настоящего пароля, никогда не выдаваемый за чей-то: им проверяют пароль при
# попытке входа с несуществующим email, чтобы обе ветки занимали одинаковое время.
PASSWORD_DUMMY_HASH = _hasher.hash("пароль-не-существует-ни-у-кого")


def hash_password(password: str) -> str:
    """Argon2id в формате PHC: соль и параметры внутри хеша."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Битый хеш считается неверным паролем, а не ошибкой разбора."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def create_access_token(user_id: uuid.UUID) -> str:
    """JWT HS256 с ``sub`` и ``exp``."""
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def read_access_token(token: str) -> uuid.UUID | None:
    """Разобрать токен. ``None`` вместо исключения: клиенту не полезно знать причину."""
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
        return uuid.UUID(payload["sub"])
    except (InvalidTokenError, KeyError, ValueError):
        return None


def set_session_cookie(response: Response, user_id: uuid.UUID) -> None:
    """Выдать cookie ``session``: HttpOnly, SameSite=Lax, Path=/, Secure в проде."""
    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE,
        value=create_access_token(user_id),
        httponly=True,
        samesite="lax",
        path="/",
        secure=settings.cookie_secure,
        max_age=settings.access_token_ttl_minutes * 60,
    )


def clear_session_cookie(response: Response) -> None:
    """Сбросить cookie сессии с теми же атрибутами, что и при выдаче."""
    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        secure=get_settings().cookie_secure,
        httponly=True,
        samesite="lax",
    )


async def get_current_user(
    session: Annotated[AsyncSession, Depends(get_session)],
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> User:
    """Текущий пользователь по cookie. Без валидного токена — 401."""
    if session_token is None:
        raise ApiError(401, UNAUTHENTICATED, "Требуется вход")
    user_id = read_access_token(session_token)
    if user_id is None:
        raise ApiError(401, UNAUTHENTICATED, "Сессия истекла или повреждена")
    user = await users.get_by_id(session, user_id)
    if user is None or not user.is_active:
        raise ApiError(401, UNAUTHENTICATED, "Сессия истекла или повреждена")
    return user
