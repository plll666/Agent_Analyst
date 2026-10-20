"""Построение модели: валидация, обёртки и повтор с текстом ошибки."""

import pytest

from app.agent.llm import LLMResponseError
from app.agent.modeler import build_model
from tests.agent.support import FailingLLM, FakeLLM, model_payload


async def test_builds_valid_model_and_passes_requirement_text() -> None:
    client = FakeLLM(model_payload())

    model = await build_model(
        client, requirement_text="Заявку можно исполнить после согласования", attempts=3
    )

    assert [variable.name for variable in model.variables]
    assert [prop.id for prop in model.properties]
    assert "Заявку можно исполнить после согласования" in client.calls[0]["user"]


async def test_accepts_document_wrapped_by_model() -> None:
    client = FakeLLM({"model": model_payload()})

    model = await build_model(client, requirement_text="текст", attempts=1)

    assert model.transitions


async def test_repairs_invalid_document_on_second_attempt() -> None:
    client = FakeLLM({"variables": []}, model_payload())

    model = await build_model(client, requirement_text="текст", attempts=2)

    assert model.initial
    assert len(client.calls) == 2
    assert "не прошёл проверку" in client.calls[1]["user"]


async def test_gives_up_after_configured_attempts() -> None:
    client = FakeLLM({"variables": []}, {"variables": []})

    with pytest.raises(LLMResponseError) as raised:
        await build_model(client, requirement_text="текст", attempts=2)

    assert len(client.calls) == 2
    assert raised.value.problems


async def test_retries_transport_failure_before_failing() -> None:
    client = FailingLLM(1, model_payload())

    model = await build_model(client, requirement_text="текст", attempts=2)

    assert model.variables
    assert len(client.calls) == 1
