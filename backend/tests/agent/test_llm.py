"""Клиент LLM: официальный SDK OpenAI плюс Instructor для структуры ответа.

Тесты гоняют настоящий SDK по подставному транспорту: проверяется не наш разбор
JSON, а то, что реально уходит в провайдер и что возвращается из клиента.
"""

import json
import logging
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from app.agent.llm import (
    LLMConfigurationError,
    LLMError,
    LLMResponseError,
    LLMSettings,
    OpenAILLMClient,
    client_from_env,
)
from tests.agent.support import settings


class Answer(BaseModel):
    """Модель ответа для тестов: одно целое поле."""

    value: int


def _client(
    handler: Callable[[httpx.Request], httpx.Response],
    **overrides: Any,
) -> OpenAILLMClient:
    return OpenAILLMClient(
        settings(**overrides),
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def _completion(content: str, usage: dict[str, int] | None = None) -> httpx.Response:
    """Конверт ``chat/completions`` с текстовым ответом модели."""
    body: dict[str, Any] = {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 0,
        "model": "test-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }
    if usage is not None:
        body["usage"] = usage
    return httpx.Response(200, json=body)


def _tool_completion(arguments: str, name: str = "Answer") -> httpx.Response:
    """Конверт с вызовом инструмента — так отвечает режим ``tools``."""
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-2",
            "object": "chat.completion",
            "created": 0,
            "model": "test-model",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "type": "function",
                                "function": {"name": name, "arguments": arguments},
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
        },
    )


async def test_returns_the_model_and_asks_for_json_object() -> None:
    """Ответ приходит разобранной моделью, запрос — в формате json_object."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _completion('{"value": 42}')

    client = _client(handler)

    answer = await client.parse(
        Answer, system="система", user="данные", prompt_version="v1", attempts=1
    )

    assert answer.value == 42
    body = json.loads(captured[0].content)
    assert captured[0].url == "https://llm.example/v1/chat/completions"
    assert body["model"] == "test-model"
    assert body["response_format"] == {"type": "json_object"}
    assert captured[0].headers["authorization"] == "Bearer key"
    # Схема ответа уходит модели в системном сообщении: json_object её не проверяет.
    system = body["messages"][0]
    assert system["role"] == "system"
    assert "json_schema" in system["content"]
    assert '"value"' in system["content"]
    assert body["messages"][1] == {"role": "user", "content": "данные"}


async def test_logs_model_prompt_version_and_token_usage(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """В лог попадают модель, версия промпта и токены — по ним считается стоимость."""
    usage = {"prompt_tokens": 120, "completion_tokens": 34, "total_tokens": 154}
    client = _client(lambda _request: _completion('{"value": 1}', usage=usage))

    with caplog.at_level(logging.INFO, logger="app.agent.llm"):
        await client.parse(Answer, system="s", user="u", prompt_version="modeling-1", attempts=1)

    message = next(item.getMessage() for item in caplog.records if item.name == "app.agent.llm")
    assert "model=test-model" in message
    assert "prompt_version=modeling-1" in message
    assert "prompt_tokens=120" in message
    assert "total_tokens=154" in message


async def test_repeats_with_the_error_text_when_the_document_is_invalid() -> None:
    """Негодный документ не выбрасывается: модель получает текст ошибки и чинит его."""
    bodies: list[dict[str, Any]] = []
    answers = ['{"nope": 1}', '{"value": 7}']

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return _completion(answers[len(bodies) - 1])

    client = _client(handler)

    answer = await client.parse(Answer, system="s", user="u", prompt_version="v1", attempts=2)

    assert answer.value == 7
    assert len(bodies) == 2
    repair = bodies[1]["messages"][-1]
    assert repair["role"] == "user"
    assert "value" in repair["content"]


async def test_exhausted_attempts_become_a_response_error() -> None:
    """Если пригодного ответа нет за все попытки — это LLMResponseError с причинами."""
    client = _client(lambda _request: _completion('{"nope": 1}'))

    with pytest.raises(LLMResponseError) as raised:
        await client.parse(Answer, system="s", user="u", prompt_version="v1", attempts=2)

    assert len(raised.value.problems) == 2
    assert "value" in raised.value.problems[-1]


async def test_non_retryable_http_error_becomes_llm_error() -> None:
    """Ошибка запроса не повторяется: повтор не исправит неверный запрос."""
    calls: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(400, json={"error": {"message": "bad request"}})

    client = _client(handler, transport_retries=2, transport_backoff_seconds=0)

    with pytest.raises(LLMError, match="запрос к LLM не удался"):
        await client.parse(Answer, system="s", user="u", prompt_version="v1", attempts=1)

    assert len(calls) == 1


async def test_tools_mode_asks_for_a_tool_call() -> None:
    """Режим ``tools`` передаёт схему вызовом инструмента — для провайдеров с tools."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _tool_completion('{"value": 5}')

    client = _client(handler, structured_mode="tools")

    answer = await client.parse(Answer, system="s", user="u", prompt_version="v1", attempts=1)

    assert answer.value == 5
    body = json.loads(captured[0].content)
    assert body["tools"][0]["function"]["name"] == "Answer"
    assert body["tools"][0]["function"]["parameters"]["properties"]["value"]["type"] == "integer"
    assert "response_format" not in body


def test_unconfigured_provider_is_reported_before_request() -> None:
    """Без ключа клиент не создаётся: понятная ошибка вместо 401 от провайдера."""
    with pytest.raises(LLMConfigurationError, match="LLM_API_KEY"):
        client_from_env({"LLM_BASE_URL": "https://llm.example/v1", "LLM_MODEL": "m"})


def test_unknown_structured_mode_is_rejected() -> None:
    """Опечатка в режиме — ошибка настройки, а не тихий откат в json_object."""
    with pytest.raises(LLMConfigurationError, match="LLM_STRUCTURED_MODE"):
        OpenAILLMClient(settings(structured_mode="yaml"))


def test_settings_accept_a_full_endpoint_and_normalise_it() -> None:
    """В окружении может оказаться полный адрес — клиенту нужен корень API."""
    configured = LLMSettings.from_env(
        {
            "LLM_BASE_URL": "https://llm.example/v1/chat/completions",
            "LLM_API_KEY": "key",
            "LLM_MODEL": "m",
        }
    )

    assert configured.base_url == "https://llm.example/v1"
    assert configured.structured_mode == "json"


async def test_reasoning_choice_is_sent_as_effort() -> None:
    """Галочка превращается в ``reasoning_effort``: включено — усилие, выключено — none."""
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return _completion('{"value": 1}')

    client = _client(handler)

    await client.parse(
        Answer, system="s", user="u", prompt_version="v1", attempts=1, reasoning=False
    )
    await client.parse(
        Answer, system="s", user="u", prompt_version="v1", attempts=1, reasoning=True
    )
    await client.parse(Answer, system="s", user="u", prompt_version="v1", attempts=1)

    assert bodies[0]["reasoning_effort"] == "none"
    assert bodies[1]["reasoning_effort"] == "high"
    # Без выбора режима параметр не передаётся: работает умолчание провайдера.
    assert "reasoning_effort" not in bodies[2]


async def test_transport_error_is_retried() -> None:
    """Обрыв соединения повторяется с паузой, а не превращается в AGENT_ERROR сразу."""
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectError("connection refused", request=request)
        return _completion('{"value": 5}')

    client = _client(handler, transport_retries=2, transport_backoff_seconds=0)

    answer = await client.parse(Answer, system="s", user="u", prompt_version="v1", attempts=1)

    assert answer.value == 5
    assert len(calls) == 2


async def test_rate_limit_is_retried() -> None:
    """429 от шлюза — временный отказ: запрос повторяется, а не падает в AGENT_ERROR."""
    calls: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(
                429,
                json={"error": {"message": "rate limited", "type": "rate_limit_error"}},
            )
        return _completion('{"value": 5}')

    client = _client(handler, transport_retries=1, transport_backoff_seconds=0)

    answer = await client.parse(Answer, system="s", user="u", prompt_version="v1", attempts=1)

    assert answer.value == 5
    assert len(calls) == 2


async def test_server_error_is_retried() -> None:
    """5xx — временный отказ провайдера, его тоже нужно повторить."""
    calls: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(500, json={"error": {"message": "boom"}})
        return _completion('{"value": 5}')

    client = _client(handler, transport_retries=1, transport_backoff_seconds=0)

    answer = await client.parse(Answer, system="s", user="u", prompt_version="v1", attempts=1)

    assert answer.value == 5
    assert len(calls) == 2


async def test_transport_retries_are_limited() -> None:
    """Когда повторы исчерпаны, отказ провайдера остаётся ошибкой провайдера."""
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise httpx.ConnectError("connection refused", request=request)

    client = _client(handler, transport_retries=1, transport_backoff_seconds=0)

    with pytest.raises(LLMError, match="запрос к LLM не удался"):
        await client.parse(Answer, system="s", user="u", prompt_version="v1", attempts=1)

    assert len(calls) == 2
