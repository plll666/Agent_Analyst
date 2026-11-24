"""Контракты импорта, повторного запуска и отмены на настоящей БД."""

import io
import uuid

import httpx
import pytest
from docx import Document
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import runs

pytestmark = pytest.mark.integration


async def _project(client: httpx.AsyncClient) -> str:
    response = await client.post("/api/projects", json={"name": "Спринт 3"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_txt_import_confirmation_and_error(registered: httpx.AsyncClient) -> None:
    project_id = await _project(registered)
    base = f"/api/projects/{project_id}"
    capabilities = await registered.get(f"{base}/requirement-imports/capabilities")
    assert capabilities.status_code == 200
    assert capabilities.json()["formats"] == ["txt", "docx"]

    uploaded = await registered.post(
        f"{base}/requirement-imports",
        files={"file": ("rules.txt", "Правило 😀\nОтмена".encode(), "text/plain")},
    )
    assert uploaded.status_code == 201, uploaded.text
    preview = uploaded.json()
    assert preview["raw_text"] == "Правило 😀\n\nОтмена"
    assert (
        preview["raw_text"][preview["fragments"][1]["start"] : preview["fragments"][1]["end"]]
        == "Отмена"
    )

    confirmed = await registered.post(
        f"{base}/requirements",
        json={"raw_text": "Исправленное правило", "source_import_id": preview["id"]},
    )
    assert confirmed.status_code == 201, confirmed.text
    assert confirmed.json()["source_modified"] is True
    assert confirmed.json()["source_import_id"] == preview["id"]
    assert confirmed.json()["fragments"][0]["source_locator"] is None

    empty = await registered.post(
        f"{base}/requirement-imports", files={"file": ("empty.txt", b"", "text/plain")}
    )
    assert empty.status_code == 422
    assert empty.json()["detail"]["code"] == "EMPTY_DOCUMENT"


async def test_docx_table_import(registered: httpx.AsyncClient) -> None:
    project_id = await _project(registered)
    document = Document()
    document.add_paragraph("Согласование")
    document.add_table(rows=1, cols=1).cell(0, 0).text = "Отмена"
    stream = io.BytesIO()
    document.save(stream)

    response = await registered.post(
        f"/api/projects/{project_id}/requirement-imports",
        files={
            "file": (
                "rules.docx",
                stream.getvalue(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["raw_text"] == "Согласование\n\nОтмена"
    assert response.json()["fragments"][1]["kind"] == "table_cell"


async def test_reuse_force_and_cancel(
    registered: httpx.AsyncClient,
    session: AsyncSession,
    enqueued: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "key")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    project_id = await _project(registered)
    base = f"/api/projects/{project_id}"
    requirement = await registered.post(
        f"{base}/requirements", json={"raw_text": "Заявку можно отменить"}
    )
    assert requirement.status_code == 201

    first = await registered.post(f"{base}/analyses", json={})
    assert first.status_code == 201, first.text
    first_id = first.json()["id"]
    joined = await registered.post(f"{base}/analyses", json={})
    assert joined.status_code == 200
    assert joined.json()["id"] == first_id
    assert joined.json()["submission"]["mode"] == "IN_PROGRESS"
    assert enqueued == [first_id]

    await runs.save_result(
        session,
        uuid.UUID(first_id),
        status="PROPERTY_HOLDS",
        engine="TLC",
        property_id="P1",
        business_summary="Проверено",
    )
    await session.commit()
    reused = await registered.post(f"{base}/analyses", json={})
    assert reused.status_code == 200
    assert reused.json()["id"] == first_id
    assert reused.json()["submission"]["mode"] == "REUSED"
    assert enqueued == [first_id]

    forced = await registered.post(f"{base}/analyses", json={"force_recompute": True})
    assert forced.status_code == 201
    assert forced.json()["id"] != first_id
    assert forced.json()["submission"]["mode"] == "CREATED"

    cancelled = await registered.post(f"{base}/analyses/{forced.json()['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    assert cancelled.json()["execution_status"] == "CANCELLED"
    events = await registered.get(f"{base}/verifications/{forced.json()['id']}/events")
    assert events.status_code == 200
    assert events.json()["items"][-1]["type"] == "run.finished"
