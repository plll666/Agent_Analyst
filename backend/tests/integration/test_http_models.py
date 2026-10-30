"""Построение модели агентом через HTTP: права, версии и отказ без записи."""

import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm import LLMConfigurationError
from app.api import analysis
from app.database.models import ModelVersion
from app.main import app
from app.repositories import projects as projects_repo
from tests.agent.support import FakeLLM, model_payload

pytestmark = pytest.mark.integration


async def _new_project(client: httpx.AsyncClient, name: str = "Заявки") -> dict[str, Any]:
    response = await client.post("/api/projects", json={"name": name})
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


async def _new_requirement(
    client: httpx.AsyncClient,
    project_id: str,
    text: str = "Заявку можно исполнить после согласования",
) -> dict[str, Any]:
    response = await client.post(
        f"/api/projects/{project_id}/requirements", json={"raw_text": text}
    )
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


def _code(response: httpx.Response) -> str:
    return str(response.json()["detail"]["code"])


def _use(fake: FakeLLM) -> None:
    app.dependency_overrides[analysis.get_llm_factory] = lambda: lambda: fake


async def _models(session: AsyncSession, project_id: str) -> list[ModelVersion]:
    statement = select(ModelVersion).where(ModelVersion.project_id == uuid.UUID(project_id))
    return list(await session.scalars(statement))


async def test_builds_model_and_links_requirement(
    registered: httpx.AsyncClient, session: AsyncSession
) -> None:
    project = await _new_project(registered)
    requirement = await _new_requirement(registered, project["id"])
    fake = FakeLLM(model_payload())
    _use(fake)

    response = await registered.post(f"/api/projects/{project['id']}/models", json={})

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["version"] == 1
    assert body["source"] == "agent"
    assert body["validation_status"] == "VALID"
    assert body["requirement_id"] == requirement["id"]
    assert body["document"]["variables"]
    assert "Заявку можно исполнить" in fake.calls[0]["user"]

    rows = await _models(session, project["id"])
    assert [str(row.requirement_id) for row in rows] == [requirement["id"]]


async def test_second_build_appends_version(
    registered: httpx.AsyncClient, session: AsyncSession
) -> None:
    project = await _new_project(registered)
    await _new_requirement(registered, project["id"])
    _use(FakeLLM(model_payload(), model_payload()))

    first = await registered.post(f"/api/projects/{project['id']}/models", json={})
    second = await registered.post(f"/api/projects/{project['id']}/models", json={})

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert (first.json()["version"], second.json()["version"]) == (1, 2)
    assert len(await _models(session, project["id"])) == 2


async def test_builds_from_explicit_requirement_version(registered: httpx.AsyncClient) -> None:
    project = await _new_project(registered)
    await _new_requirement(registered, project["id"], "старый текст")
    fresh = await _new_requirement(registered, project["id"], "новый текст")
    fake = FakeLLM(model_payload())
    _use(fake)

    response = await registered.post(
        f"/api/projects/{project['id']}/models", json={"requirement_id": fresh["id"]}
    )

    assert response.status_code == 201, response.text
    assert response.json()["requirement_id"] == fresh["id"]
    assert "новый текст" in fake.calls[0]["user"]


async def test_requirement_from_another_project_is_404(
    registered: httpx.AsyncClient,
) -> None:
    first = await _new_project(registered, "Первый")
    second = await _new_project(registered, "Второй")
    foreign_requirement = await _new_requirement(registered, first["id"])
    _use(FakeLLM(model_payload()))

    response = await registered.post(
        f"/api/projects/{second['id']}/models",
        json={"requirement_id": foreign_requirement["id"]},
    )

    assert response.status_code == 404
    assert _code(response) == "NOT_FOUND"


async def test_without_requirement_is_422_and_llm_is_not_called(
    registered: httpx.AsyncClient,
) -> None:
    project = await _new_project(registered)
    fake = FakeLLM(model_payload())
    _use(fake)

    response = await registered.post(f"/api/projects/{project['id']}/models", json={})

    assert response.status_code == 422
    assert _code(response) == "VALIDATION_ERROR"
    assert fake.calls == []


async def test_foreign_project_is_403(
    registered: httpx.AsyncClient, session: AsyncSession, owner_id: uuid.UUID
) -> None:
    foreign = await projects_repo.create(session, owner_id=owner_id, name="Чужой")
    await session.flush()
    _use(FakeLLM(model_payload()))

    response = await registered.post(f"/api/projects/{foreign.id}/models", json={})

    assert response.status_code == 403
    assert _code(response) == "FORBIDDEN"


async def test_invalid_model_after_retries_is_422_and_not_saved(
    registered: httpx.AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await _new_project(registered)
    await _new_requirement(registered, project["id"])
    monkeypatch.setenv("LLM_MAX_ATTEMPTS", "2")
    _use(FakeLLM({"variables": []}, {"variables": []}))

    response = await registered.post(f"/api/projects/{project['id']}/models", json={})

    assert response.status_code == 422, response.text
    assert _code(response) == "VALIDATION_ERROR"
    assert "Агент не смог построить модель" in response.json()["detail"]["message"]
    count = await session.scalar(
        select(func.count())
        .select_from(ModelVersion)
        .where(ModelVersion.project_id == uuid.UUID(project["id"]))
    )
    assert count == 0


async def test_unconfigured_provider_is_503(registered: httpx.AsyncClient) -> None:
    project = await _new_project(registered)
    await _new_requirement(registered, project["id"])

    def unconfigured() -> FakeLLM:
        raise LLMConfigurationError("LLM не настроена: не заданы LLM_API_KEY")

    app.dependency_overrides[analysis.get_llm_factory] = lambda: unconfigured

    response = await registered.post(f"/api/projects/{project['id']}/models", json={})

    assert response.status_code == 503
    assert _code(response) == "LLM_UNAVAILABLE"
