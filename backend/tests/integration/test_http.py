"""HTTP-слой: контракт с фронтендом, cookie-сессия и границы доступа."""

import uuid
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import auth
from app.api.projects import ProjectOut
from app.auth import MIN_PASSWORD_LENGTH, PASSWORD_DUMMY_HASH, verify_password
from app.errors import install_exception_handlers
from app.repositories import projects as projects_repo
from app.repositories import runs, users
from tests.integration.conftest import case_document

pytestmark = pytest.mark.integration


async def _new_project(client: httpx.AsyncClient, name: str = "Чек-лист") -> dict[str, Any]:
    response = await client.post("/api/projects", json={"name": name})
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


async def _new_requirement(client: httpx.AsyncClient, project_id: str) -> dict[str, Any]:
    response = await client.post(
        f"/api/projects/{project_id}/requirements",
        json={"raw_text": "Проверка воспроизводима"},
    )
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


def _code(response: httpx.Response) -> str:
    return str(response.json()["detail"]["code"])


# --- регистрация, вход, выход ---


async def test_register_returns_user_without_password_material(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/auth/register",
        json={"email": "anna@example.com", "password": "correct-horse", "display_name": "Анна"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == "anna@example.com"
    assert body["display_name"] == "Анна"
    assert "password" not in body
    assert "password_hash" not in body


async def test_register_sets_hardened_session_cookie(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/auth/register",
        json={"email": "cookie@example.com", "password": "correct-horse"},
    )

    cookie = response.headers["set-cookie"].lower()
    assert "session=" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "path=/" in cookie
    assert "jwt" not in cookie


async def test_register_rejects_taken_email(client: httpx.AsyncClient) -> None:
    payload = {"email": "taken@example.com", "password": "correct-horse"}
    assert (await client.post("/api/auth/register", json=payload)).status_code == 201

    second = await client.post("/api/auth/register", json=payload)

    assert second.status_code == 409
    assert _code(second) == "EMAIL_TAKEN"


async def test_concurrent_registration_of_same_email_returns_conflict(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Гонка: единственный барьер — уникальный индекс."""
    payload = {"email": "race@example.com", "password": "correct-horse"}
    assert (await client.post("/api/auth/register", json=payload)).status_code == 201

    async def always_free(_session: AsyncSession, _email: str) -> None:
        return None

    monkeypatch.setattr(users, "get_by_email_lower", always_free)

    raced = await client.post("/api/auth/register", json=payload)

    assert raced.status_code == 409
    assert _code(raced) == "EMAIL_TAKEN"


async def test_login_accepts_own_credentials(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/auth/register",
        json={"email": "in@example.com", "password": "correct-horse"},
    )
    await client.post("/api/auth/logout")

    response = await client.post(
        "/api/auth/login", json={"email": "in@example.com", "password": "correct-horse"}
    )

    assert response.status_code == 200, response.text
    assert "session" in response.cookies
    assert (await client.get("/api/auth/me")).status_code == 200


async def test_login_failure_does_not_reveal_whether_email_exists(
    client: httpx.AsyncClient,
) -> None:
    await client.post(
        "/api/auth/register",
        json={"email": "known@example.com", "password": "correct-horse"},
    )
    await client.post("/api/auth/logout")

    wrong_password = await client.post(
        "/api/auth/login", json={"email": "known@example.com", "password": "wrong-password"}
    )
    unknown_email = await client.post(
        "/api/auth/login", json={"email": "ghost@example.com", "password": "correct-horse"}
    )

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    assert _code(wrong_password) == _code(unknown_email) == "INVALID_CREDENTIALS"


async def test_unknown_email_still_spends_time_on_password_check(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Несуществующий email не должен проверяться быстрее существующего."""
    await client.post(
        "/api/auth/register",
        json={"email": "timing@example.com", "password": "correct-horse"},
    )
    checked: list[tuple[str, str]] = []
    original = verify_password

    def spy(password: str, password_hash: str) -> bool:
        checked.append((password, password_hash))
        return original(password, password_hash)

    monkeypatch.setattr(auth, "verify_password", spy)

    await client.post("/api/auth/login", json={"email": "timing@example.com", "password": "wrong"})
    await client.post("/api/auth/login", json={"email": "ghost@example.com", "password": "any"})

    assert len(checked) == 2, "пароль не проверен ни для одной из веток"
    assert checked[1][1] == PASSWORD_DUMMY_HASH


async def test_logout_ends_the_session(registered: httpx.AsyncClient) -> None:
    assert (await registered.get("/api/auth/me")).status_code == 200

    await registered.post("/api/auth/logout")

    assert (await registered.get("/api/auth/me")).status_code == 401
    assert (await registered.get("/api/projects")).status_code == 401


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/auth/me"),
        ("GET", "/api/projects"),
        ("GET", "/api/users/me/summary"),
    ],
)
async def test_anonymous_request_is_unauthenticated(
    client: httpx.AsyncClient, method: str, path: str
) -> None:
    response = await client.request(method, path)

    assert response.status_code == 401
    assert _code(response) == "UNAUTHENTICATED"


# --- проекты ---


async def test_project_crud(registered: httpx.AsyncClient) -> None:
    created = await _new_project(registered, "Заявки")
    project_id = created["id"]

    listed = await registered.get("/api/projects")
    assert [item["id"] for item in listed.json()["items"]] == [project_id]

    fetched = await registered.get(f"/api/projects/{project_id}")
    assert fetched.json()["name"] == "Заявки"

    renamed = await registered.patch(f"/api/projects/{project_id}", json={"name": "Заявки v2"})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "Заявки v2"
    assert renamed.json()["updated_at"] >= created["updated_at"]


async def test_project_list_contains_only_own_projects(
    registered: httpx.AsyncClient, session: AsyncSession, owner_id: uuid.UUID
) -> None:
    mine = await _new_project(registered, "Мой")
    await projects_repo.create(session, owner_id=owner_id, name="Чужой")

    listed = await registered.get("/api/projects")

    assert [item["id"] for item in listed.json()["items"]] == [mine["id"]]


async def test_foreign_project_is_403_and_missing_is_404(
    registered: httpx.AsyncClient, session: AsyncSession, owner_id: uuid.UUID
) -> None:
    foreign = await projects_repo.create(session, owner_id=owner_id, name="Чужой")
    await session.flush()

    forbidden = await registered.get(f"/api/projects/{foreign.id}")
    missing = await registered.get(f"/api/projects/{uuid.uuid4()}")

    assert forbidden.status_code == 403
    assert _code(forbidden) == "FORBIDDEN"
    assert missing.status_code == 404
    assert _code(missing) == "NOT_FOUND"


async def test_patch_cannot_rename_foreign_project(
    registered: httpx.AsyncClient, session: AsyncSession, owner_id: uuid.UUID
) -> None:
    foreign = await projects_repo.create(session, owner_id=owner_id, name="Чужой")
    await session.flush()

    response = await registered.patch(f"/api/projects/{foreign.id}", json={"name": "Украдено"})

    assert response.status_code == 403


async def test_project_name_must_not_be_empty(registered: httpx.AsyncClient) -> None:
    response = await registered.post("/api/projects", json={"name": ""})

    assert response.status_code == 422
    assert _code(response) == "VALIDATION_ERROR"


# --- требования ---


async def test_requirement_versions_are_appended_and_ordered(
    registered: httpx.AsyncClient,
) -> None:
    project = await _new_project(registered)

    first = await registered.post(
        f"/api/projects/{project['id']}/requirements", json={"raw_text": "первая"}
    )
    second = await registered.post(
        f"/api/projects/{project['id']}/requirements", json={"raw_text": "вторая"}
    )
    assert first.status_code == second.status_code == 201
    assert first.json()["version"] == 1
    assert second.json()["version"] == 2
    assert second.json()["is_current"] is True

    listed = await registered.get(f"/api/projects/{project['id']}/requirements")
    assert [item["version"] for item in listed.json()["items"]] == [2, 1]

    stale = await registered.get(f"/api/requirements/{first.json()['id']}")
    assert stale.json()["is_current"] is False
    fresh = await registered.get(f"/api/requirements/{second.json()['id']}")
    assert fresh.json()["is_current"] is True


async def test_requirement_by_id(registered: httpx.AsyncClient) -> None:
    project = await _new_project(registered)
    created = await _new_requirement(registered, project["id"])

    response = await registered.get(f"/api/requirements/{created['id']}")

    assert response.status_code == 200
    assert response.json()["raw_text"] == "Проверка воспроизводима"


async def test_foreign_requirement_is_403(
    registered: httpx.AsyncClient, session: AsyncSession, owner_id: uuid.UUID
) -> None:
    foreign = await projects_repo.create(session, owner_id=owner_id, name="Чужой")
    await session.flush()
    version = await projects_repo.add_requirement_version(
        session, foreign.id, raw_text="их требование"
    )
    assert version is not None

    forbidden = await registered.get(f"/api/requirements/{version.id}")
    missing = await registered.get(f"/api/requirements/{uuid.uuid4()}")

    assert forbidden.status_code == 403
    assert missing.status_code == 404


async def test_cannot_add_requirement_to_foreign_project(
    registered: httpx.AsyncClient, session: AsyncSession, owner_id: uuid.UUID
) -> None:
    foreign = await projects_repo.create(session, owner_id=owner_id, name="Чужой")
    await session.flush()

    response = await registered.post(
        f"/api/projects/{foreign.id}/requirements", json={"raw_text": "подмена"}
    )

    assert response.status_code == 403


# --- анализ ---


async def _seed_model(session: AsyncSession, project_id: str) -> None:
    await runs.create_model_version(
        session,
        uuid.UUID(project_id),
        version=1,
        source="agent",
        document=case_document(),
        schema_hash="a" * 64,
        validation_status="VALID",
    )
    await session.flush()


async def test_start_verification_without_model_is_422(registered: httpx.AsyncClient) -> None:
    project = await _new_project(registered)

    response = await registered.post(f"/api/projects/{project['id']}/verifications")

    assert response.status_code == 422
    assert _code(response) == "VALIDATION_ERROR"


async def test_start_verification_returns_pending_run(
    registered: httpx.AsyncClient, session: AsyncSession
) -> None:
    """Запуск отдаёт PENDING: результат проверки пишет воркер, а не HTTP-запрос."""
    project = await _new_project(registered)
    await _seed_model(session, project["id"])

    response = await registered.post(f"/api/projects/{project['id']}/verifications")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "PENDING"
    assert body["business_summary"] == ""
    assert body["project_id"] == project["id"]
    assert body["model_version_id"]
    assert "counterexample" not in body
    assert "property_id" not in body


async def test_start_verification_enqueues_the_run(
    registered: httpx.AsyncClient, session: AsyncSession, enqueued: list[str]
) -> None:
    """В очередь кладётся именно эта строка: воркер читает модель по её id."""
    project = await _new_project(registered)
    await _seed_model(session, project["id"])

    created = (await registered.post(f"/api/projects/{project['id']}/verifications")).json()

    assert enqueued == [created["id"]]


async def test_started_verification_is_readable_afterwards(
    registered: httpx.AsyncClient, session: AsyncSession
) -> None:
    project = await _new_project(registered)
    await _seed_model(session, project["id"])
    created = (await registered.post(f"/api/projects/{project['id']}/verifications")).json()

    listed = await registered.get(f"/api/projects/{project['id']}/verifications")

    assert [item["id"] for item in listed.json()["items"]] == [created["id"]]
    assert listed.json()["items"][0]["status"] == "PENDING"


async def test_model_versions_are_exposed_for_owner(
    registered: httpx.AsyncClient, session: AsyncSession
) -> None:
    project = await _new_project(registered)
    await _seed_model(session, project["id"])

    listed = await registered.get(f"/api/projects/{project['id']}/models")

    assert listed.status_code == 200, listed.text
    item = listed.json()["items"][0]
    assert item["version"] == 1
    assert item["validation_status"] == "VALID"
    assert item["document"]["properties"][0]["id"] == "P1"


async def test_cannot_run_analysis_on_foreign_project(
    registered: httpx.AsyncClient, session: AsyncSession, owner_id: uuid.UUID
) -> None:
    foreign = await projects_repo.create(session, owner_id=owner_id, name="Чужой")
    await session.flush()

    response = await registered.post(f"/api/projects/{foreign.id}/verifications")

    assert response.status_code == 403


# --- профиль ---


async def test_profile_summary_counts_only_own_rows(
    registered: httpx.AsyncClient, session: AsyncSession, owner_id: uuid.UUID
) -> None:
    project = await _new_project(registered)
    await _new_requirement(registered, project["id"])
    await _new_requirement(registered, project["id"])
    await _seed_model(session, project["id"])
    await registered.post(f"/api/projects/{project['id']}/verifications")

    foreign = await projects_repo.create(session, owner_id=owner_id, name="Чужой")
    await projects_repo.add_requirement_version(session, foreign.id, raw_text="их")

    response = await registered.get("/api/users/me/summary")

    assert response.status_code == 200, response.text
    summary = response.json()
    assert summary["projects_count"] == 1
    assert summary["requirement_versions_count"] == 2
    assert summary["verification_count"] == 1
    assert summary["violation_count"] == 0
    assert summary["last_verification_at"] is not None
    assert summary["user"]["email"]


# --- единый формат ошибок ---


async def test_unknown_route_keeps_error_envelope(registered: httpx.AsyncClient) -> None:
    response = await registered.get("/api/nope")

    assert response.status_code == 404
    assert set(response.json()["detail"]) == {"code", "message"}


async def test_unknown_project_id_must_be_uuid(registered: httpx.AsyncClient) -> None:
    response = await registered.get("/api/projects/not-a-uuid")

    assert response.status_code == 422
    assert _code(response) == "VALIDATION_ERROR"


async def test_wrong_method_is_not_reported_as_validation_error(
    registered: httpx.AsyncClient,
) -> None:
    """Код ошибки метода не должен выдаваться за ошибку данных."""
    response = await registered.delete("/api/projects")

    assert response.status_code == 405
    assert _code(response) == "METHOD_NOT_ALLOWED"


async def test_short_password_is_rejected_by_shared_constant(client: httpx.AsyncClient) -> None:
    """Правило длины живёт в ``auth.MIN_PASSWORD_LENGTH``."""
    response = await client.post(
        "/api/auth/register",
        json={"email": "short@example.com", "password": "x" * (MIN_PASSWORD_LENGTH - 1)},
    )

    assert response.status_code == 422
    assert _code(response) == "VALIDATION_ERROR"


async def test_password_of_exactly_minimum_length_is_accepted(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        "/api/auth/register",
        json={"email": "exact@example.com", "password": "x" * MIN_PASSWORD_LENGTH},
    )

    assert response.status_code == 201, response.text


async def test_response_model_mismatch_is_reported_as_internal_error() -> None:
    """Ответ, не сошедшийся с ``response_model``, — 500."""
    mismatched = FastAPI()
    install_exception_handlers(mismatched)

    @mismatched.get("/broken", response_model=ProjectOut)
    async def broken() -> dict[str, str]:
        """Словарь без обязательных полей ``ProjectOut``."""
        return {"name": "без идентичности"}

    transport = httpx.ASGITransport(app=mismatched)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as broken_client:
        response = await broken_client.get("/broken")

    assert response.status_code == 500
    assert _code(response) == "INTERNAL_ERROR"
    assert "updated_at" not in response.json()["detail"]["message"]
