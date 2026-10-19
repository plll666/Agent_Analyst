from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    MIN_PASSWORD_LENGTH,
    PASSWORD_DUMMY_HASH,
    clear_session_cookie,
    get_current_user,
    hash_password,
    set_session_cookie,
    verify_password,
)
from app.database.models import User
from app.db import get_session
from app.errors import EMAIL_TAKEN, INVALID_CREDENTIALS, ApiError
from app.repositories import users

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)
    display_name: str | None = Field(default=None, max_length=100)


class LoginIn(BaseModel):
    email: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1)


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str | None
    created_at: str
    last_login_at: str | None


def _to_out(user: User) -> UserOut:
    return UserOut(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        created_at=user.created_at.isoformat(),
        last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
    )


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserOut)
async def register(
    payload: RegisterIn,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserOut:
    """Регистрация и немедленный вход: cookie выдаётся вместе с 201."""
    email = payload.email.strip().lower()
    if await users.get_by_email_lower(session, email) is not None:
        raise ApiError(status.HTTP_409_CONFLICT, EMAIL_TAKEN, "Email уже занят")
    try:
        created = await users.create(
            session,
            email=email,
            password_hash=hash_password(payload.password),
            display_name=payload.display_name,
        )
    except IntegrityError as duplicate:
        # Проверка занятости выше — оптимизация, а не защита: при одновременной
        # регистрации оба запроса её пройдут. Уникальный индекс решит, кто прав.
        raise ApiError(status.HTTP_409_CONFLICT, EMAIL_TAKEN, "Email уже занят") from duplicate
    await users.touch_last_login(session, created.id)
    await session.refresh(created)
    set_session_cookie(response, created.id)
    return _to_out(created)


@router.post("/login", response_model=UserOut)
async def login(
    payload: LoginIn,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserOut:
    """Неверный email и неверный пароль дают одну ошибку: существование email не утекает."""
    found = await users.get_by_email_lower(session, payload.email)
    if found is None:
        # Пароль проверяется и здесь — по хешу-заглушке. Иначе несуществующий email
        # отвечал бы заметно быстрее существующего с неверным паролем.
        verify_password(payload.password, PASSWORD_DUMMY_HASH)
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED, INVALID_CREDENTIALS, "Неверный email или пароль"
        )
    if not verify_password(payload.password, found.password_hash) or not found.is_active:
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED, INVALID_CREDENTIALS, "Неверный email или пароль"
        )
    await users.touch_last_login(session, found.id)
    await session.refresh(found)
    set_session_cookie(response, found.id)
    return _to_out(found)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    """Сбросить cookie сессии."""
    clear_session_cookie(response)


@router.get("/me", response_model=UserOut)
async def me(user: Annotated[User, Depends(get_current_user)]) -> UserOut:
    """Текущий пользователь по cookie."""
    return _to_out(user)
