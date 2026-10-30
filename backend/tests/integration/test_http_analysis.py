"""HTTP-слой агентного цикла: запуск анализа и ответ на вопрос агента."""

import uuid
from typing import Any

import httpx
import pytest

from app.agent.capabilities import ReasoningCapability
from app.api import analysis
from app.repositories import runs

pytestmark = pytest.mark.integration

REQUIREMENT_TEXT = (
    "Заявка после согласования может быть исполнена. "
    "Пользователь может отменить заявку до исполнения."
)


@pytest.fixture(autouse=True)
def configured_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Провайдер настроен: иначе запуск анализа отвечает 503."""
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "key")
    monkeypatch.setenv("LLM_MODEL", "test-model")


async def _project_with_requirement(client: httpx.AsyncClient) -> tuple[str, str]:
    """Проект с текстом требования."""
    response = await client.post("/api/projects", json={"name": "Кейс 2"})
    assert response.status_code == 201, response.text
    project_id = response.json()["id"]
    response = await client.post(
        f"/api/projects/{project_id}/requirements", json={"raw_text": REQUIREMENT_TEXT}
    )
    assert response.status_code == 201, response.text
    return project_id, response.json()["id"]


async def test_start_analysis_creates_pending_run(
    registered: httpx.AsyncClient, enqueued: list[str]
) -> None:
    """Анализ отвечает сразу прогоном в PENDING, а работает в фоне."""
    project_id, requirement_id = await _project_with_requirement(registered)

    response = await registered.post(f"/api/projects/{project_id}/analyses", json={})

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "PENDING"
    assert body["model_version_id"] is None
    # Прогон фиксирует версию требования: иначе воркер проверил бы тот текст,
    # который будет «текущим» к моменту запуска, а не тот, что выбрал пользователь.
    assert body["requirement_id"] == requirement_id
    assert body["business_summary"] == ""
    assert body["reasoning"] is None
    assert enqueued == [body["id"]]


async def test_start_analysis_without_requirement_is_rejected(
    registered: httpx.AsyncClient,
) -> None:
    """Анализировать нечего — текст требования должен быть."""
    response = await registered.post("/api/projects", json={"name": "Пусто"})

    project_id = response.json()["id"]
    result = await registered.post(f"/api/projects/{project_id}/analyses", json={})

    assert result.status_code == 422, result.text
    assert result.json()["detail"]["code"] == "VALIDATION_ERROR"


async def test_start_analysis_without_provider_is_rejected(
    registered: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Без провайдера анализ не запускается: 503 вместо тихого PENDING."""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    project_id, _ = await _project_with_requirement(registered)

    response = await registered.post(f"/api/projects/{project_id}/analyses", json={})

    assert response.status_code == 503, response.text
    assert response.json()["detail"]["code"] == "LLM_UNAVAILABLE"


async def test_answer_to_question_starts_next_iteration(
    registered: httpx.AsyncClient, session: Any, enqueued: list[str]
) -> None:
    """Ответ дополняет требование и запускает следующую итерацию."""
    project_id, _ = await _project_with_requirement(registered)
    started = await registered.post(f"/api/projects/{project_id}/analyses", json={})
    run_id = started.json()["id"]

    await runs.save_result(
        session,
        uuid.UUID(run_id),
        status="PROPERTY_VIOLATED",
        engine="TLC",
        business_summary="Заявку отменили, но исполнили.",
        hypothesis="В модели нет запрета на исполнение отменённой заявки.",
        question="Должна ли отменённая заявка оставаться исполнимой?",
    )
    await session.commit()
    enqueued.clear()

    response = await registered.post(
        f"/api/projects/{project_id}/analyses/{run_id}/answer",
        json={"answer": "Нет, отменённую заявку исполнять нельзя"},
    )

    assert response.status_code == 201, response.text
    next_run = response.json()
    assert next_run["status"] == "PENDING"
    assert next_run["id"] != run_id
    assert enqueued == [next_run["id"]]

    requirements = await registered.get(f"/api/projects/{project_id}/requirements")
    latest = requirements.json()["items"][0]
    # Новый прогон ссылается на уточнённую версию требования.
    assert next_run["requirement_id"] == latest["id"]
    assert latest["version"] == 2
    assert "Уточнение пользователя" in latest["raw_text"]
    assert "отменённую заявку исполнять нельзя" in latest["raw_text"]


async def test_blank_answer_is_rejected_before_new_version(
    registered: httpx.AsyncClient, session: Any, enqueued: list[str]
) -> None:
    """Ответ из пробелов не должен становиться пустым уточнением в требовании."""
    project_id, _ = await _project_with_requirement(registered)
    started = await registered.post(f"/api/projects/{project_id}/analyses", json={})
    run_id = started.json()["id"]

    await runs.save_result(
        session,
        uuid.UUID(run_id),
        status="PROPERTY_VIOLATED",
        engine="TLC",
        business_summary="Заявку отменили, но исполнили.",
        hypothesis="В модели нет запрета на исполнение отменённой заявки.",
        question="Должна ли отменённая заявка оставаться исполнимой?",
    )
    await session.commit()
    enqueued.clear()

    response = await registered.post(
        f"/api/projects/{project_id}/analyses/{run_id}/answer",
        json={"answer": "  \n\t  "},
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"
    requirements = await registered.get(f"/api/projects/{project_id}/requirements")
    assert len(requirements.json()["items"]) == 1
    assert enqueued == []


async def test_answer_to_run_without_question_is_rejected(
    registered: httpx.AsyncClient,
) -> None:
    """Отвечать не на что: у прогона без вопроса ответа быть не может."""
    project_id, _ = await _project_with_requirement(registered)
    started = await registered.post(f"/api/projects/{project_id}/analyses", json={})
    run_id = started.json()["id"]

    response = await registered.post(
        f"/api/projects/{project_id}/analyses/{run_id}/answer", json={"answer": "Что-то"}
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"


async def test_answer_to_agent_model_error_is_rejected(
    registered: httpx.AsyncClient, session: Any
) -> None:
    """Ошибку модели агент исправляет сам: вопрос к требованию не принимается."""
    project_id, _ = await _project_with_requirement(registered)
    started = await registered.post(f"/api/projects/{project_id}/analyses", json={})
    run_id = started.json()["id"]

    await runs.save_result(
        session,
        uuid.UUID(run_id),
        status="PROPERTY_VIOLATED",
        engine="TLC",
        business_summary="Отмена нарушила свойство.",
        hypothesis="Свойство запрещает отмену вместо исполнения отменённой заявки.",
        question="Должна ли отменённая заявка исполняться?",
        root_cause="AGENT_ERROR",
    )
    await session.commit()

    response = await registered.post(
        f"/api/projects/{project_id}/analyses/{run_id}/answer",
        json={"answer": "Нет, исполняться не должна"},
    )

    assert response.status_code == 422, response.text
    assert "ошибку модели" in response.json()["detail"]["message"]


async def test_answer_to_unknown_run_is_not_found(
    registered: httpx.AsyncClient,
) -> None:
    """Чужой или несуществующий прогон — 404, а не 500."""
    project_id, _ = await _project_with_requirement(registered)

    response = await registered.post(
        f"/api/projects/{project_id}/analyses/{uuid.uuid4()}/answer", json={"answer": "Уточнение"}
    )

    assert response.status_code == 404, response.text


def _capability(available: bool | None, detail: str | None = None) -> Any:
    """Подменить пробу провайдера: тесты HTTP-слоя не ходят в сеть."""

    async def detect(_settings: Any) -> ReasoningCapability:
        return ReasoningCapability(available, source="test", detail=detail)

    return detect


async def test_analysis_passes_reasoning_choice_to_worker(
    registered: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Выбор пользователя уходит в очередь и сохраняется в прогоне."""
    project_id, _ = await _project_with_requirement(registered)
    monkeypatch.setattr(analysis, "detect_reasoning", _capability(True))
    captured: list[dict[str, Any]] = []

    async def record(_verification_id: str, **kwargs: Any) -> None:
        captured.append(kwargs)

    monkeypatch.setattr(analysis, "enqueue_analysis", record)

    response = await registered.post(
        f"/api/projects/{project_id}/analyses", json={"reasoning": False}
    )

    assert response.status_code == 201, response.text
    assert captured == [{"reasoning": False}]
    assert response.json()["reasoning"] is False


async def test_reasoning_is_rejected_when_model_cannot_do_it(
    registered: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Галочку нельзя включить для модели, которая рассуждать не умеет."""
    project_id, _ = await _project_with_requirement(registered)
    monkeypatch.setattr(
        analysis, "detect_reasoning", _capability(False, "провайдер не принимает режим")
    )

    response = await registered.post(
        f"/api/projects/{project_id}/analyses", json={"reasoning": True}
    )

    assert response.status_code == 422, response.text
    assert "рассуждения" in response.json()["detail"]["message"]


async def test_capabilities_endpoint_reports_reasoning(
    registered: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Фронт спрашивает у бэка, показывать ли галочку."""
    monkeypatch.setattr(analysis, "detect_reasoning", _capability(True))

    response = await registered.get("/api/llm/capabilities")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["model"] == "test-model"
    assert body["reasoning"]["available"] is True
