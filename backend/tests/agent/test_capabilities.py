"""Проверка поддержки рассуждений: проба провайдера, кеш и ручной ответ."""

import json
from typing import Any

import httpx
import pytest

from app.agent.capabilities import detect_reasoning
from tests.agent.support import settings


def _probe_client(
    handler: Any,
) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _usage(reasoning_tokens: int) -> dict[str, Any]:
    return {
        "prompt_tokens": 10,
        "completion_tokens": reasoning_tokens + 5,
        "total_tokens": reasoning_tokens + 15,
        "completion_tokens_details": {"reasoning_tokens": reasoning_tokens},
    }


def _answer(tokens: int) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-1",
            "object": "chat.completion",
            "created": 0,
            "model": "test-model",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "391"},
                    "finish_reason": "stop",
                }
            ],
            "usage": _usage(tokens),
        },
    )


async def test_reasoning_is_available_when_it_can_be_turned_off() -> None:
    """``none`` без рассуждений, ``high`` с рассуждениями — галочка имеет смысл."""
    efforts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        effort = json.loads(request.content)["reasoning_effort"]
        efforts.append(effort)
        return _answer(0 if effort == "none" else 7)

    capability = await detect_reasoning(settings(), client=_probe_client(handler), use_cache=False)

    assert capability.available is True
    assert capability.always_on is False
    assert capability.source == "probe"
    assert efforts == ["none", "high"]


async def test_always_on_reasoning_is_reported() -> None:
    """Если ``none`` всё равно рассуждает, выключателя нет — это видно фронту."""
    capability = await detect_reasoning(
        settings(), client=_probe_client(lambda _r: _answer(4)), use_cache=False
    )

    assert capability.available is True
    assert capability.always_on is True


async def test_provider_that_rejects_effort_is_not_offered() -> None:
    """400 на ``reasoning_effort`` — модели это незнакомо, галочку не показываем."""
    capability = await detect_reasoning(
        settings(),
        client=_probe_client(
            lambda _r: httpx.Response(
                400, json={"error": {"message": "unknown parameter reasoning_effort"}}
            )
        ),
        use_cache=False,
    )

    assert capability.available is False
    assert capability.source == "probe"


async def test_model_without_reasoning_tokens_is_not_offered() -> None:
    """Параметр принят, но рассуждений нет — включать нечего."""
    capability = await detect_reasoning(
        settings(), client=_probe_client(lambda _r: _answer(0)), use_cache=False
    )

    assert capability.available is False


async def test_probe_failure_is_unknown_not_a_crash() -> None:
    """Сеть моргнула — это не «модель не умеет», а «проверить не удалось»."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    capability = await detect_reasoning(settings(), client=_probe_client(handler), use_cache=False)

    assert capability.available is None
    assert capability.source == "probe_failed"


async def test_environment_override_skips_the_probe() -> None:
    """``LLM_REASONING_SUPPORTED`` избавляет от сетевой пробы."""

    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("проба не должна выполняться")

    capability = await detect_reasoning(
        settings(reasoning_supported="true"),
        client=_probe_client(handler),
        use_cache=False,
    )

    assert capability.available is True
    assert capability.source == "env"


@pytest.mark.parametrize("value", ["false", "0", "off"])
async def test_environment_override_can_disable(value: str) -> None:
    """Обратный ответ тоже задаётся без сети."""
    capability = await detect_reasoning(settings(reasoning_supported=value), use_cache=False)

    assert capability.available is False
    assert capability.source == "env"
