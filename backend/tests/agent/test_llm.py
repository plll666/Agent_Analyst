"""HTTP-адаптер LLM: конверт запроса и разбор ответа."""

import json
import logging
from collections.abc import Callable, Mapping
from typing import Any

import httpx
import pytest

from app.agent.llm import (
    HttpLLMClient,
    LLMConfigurationError,
    LLMError,
    LLMResponseError,
    request_validated,
)
from tests.agent.support import settings


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> HttpLLMClient:
    transport = httpx.MockTransport(handler)
    return HttpLLMClient(
        settings(), client=httpx.AsyncClient(transport=transport, base_url="https://llm.example")
    )


def _envelope(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


async def test_sends_openai_compatible_request_and_parses_json() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _envelope(json.dumps({"answer": 42}))

    client = _client(handler)

    payload = await client.complete_json(system="система", user="данные", prompt_version="v1")

    assert payload == {"answer": 42}
    body = json.loads(captured[0].content)
    assert captured[0].url == "https://llm.example/v1/chat/completions"
    assert body["model"] == "test-model"
    assert body["messages"] == [
        {"role": "system", "content": "система"},
        {"role": "user", "content": "данные"},
    ]
    assert body["response_format"] == {"type": "json_object"}
    assert captured[0].headers["authorization"] == "Bearer key"


async def test_logs_model_prompt_version_and_token_usage(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps({"answer": 1})}}],
                "usage": {"prompt_tokens": 120, "completion_tokens": 34, "total_tokens": 154},
            },
        )

    client = _client(handler)

    with caplog.at_level(logging.INFO, logger="app.agent.llm"):
        await client.complete_json(system="s", user="u", prompt_version="modeling-1")

    message = next(item.getMessage() for item in caplog.records if item.name == "app.agent.llm")
    assert "model=test-model" in message
    assert "prompt_version=modeling-1" in message
    assert "prompt_tokens=120" in message
    assert "total_tokens=154" in message


async def test_strips_markdown_fence_around_json() -> None:
    client = _client(lambda _request: _envelope('```json\n{"answer": 1}\n```'))

    assert await client.complete_json(system="s", user="u", prompt_version="v1") == {"answer": 1}


async def test_http_error_becomes_llm_error() -> None:
    client = _client(lambda _request: httpx.Response(500, text="boom"))

    with pytest.raises(LLMError, match="запрос к LLM не удался"):
        await client.complete_json(system="s", user="u", prompt_version="v1")


async def test_non_json_content_becomes_llm_error() -> None:
    client = _client(lambda _request: _envelope("не JSON"))

    with pytest.raises(LLMError, match="не разбирается как JSON"):
        await client.complete_json(system="s", user="u", prompt_version="v1")


async def test_missing_choices_becomes_llm_error() -> None:
    client = _client(lambda _request: httpx.Response(200, json={"choices": []}))

    with pytest.raises(LLMError, match="нет choices"):
        await client.complete_json(system="s", user="u", prompt_version="v1")


async def test_unconfigured_provider_is_reported_before_request() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("запрос не должен уйти")

    client = HttpLLMClient(
        settings(api_key=""), client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )

    with pytest.raises(LLMConfigurationError, match="LLM_API_KEY"):
        await client.complete_json(system="s", user="u", prompt_version="v1")


async def test_request_validated_repeats_with_problems() -> None:
    class OnceInvalid:
        def __init__(self) -> None:
            self.calls = 0

        async def complete_json(
            self, *, system: str, user: str, prompt_version: str
        ) -> dict[str, object]:
            del system, user, prompt_version
            self.calls += 1
            return {"bad": True}

        async def aclose(self) -> None:
            return None

    def parse(payload: Mapping[str, Any]) -> str:
        if "bad" in payload:
            raise ValueError("поле bad запрещено")
        return str(payload["good"])

    client = OnceInvalid()
    with pytest.raises(LLMResponseError):
        await request_validated(
            client,
            system="s",
            user="u",
            prompt_version="v1",
            attempts=2,
            parse=parse,
        )

    assert client.calls == 2
