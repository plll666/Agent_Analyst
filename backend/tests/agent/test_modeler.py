"""Построение модели: доменная форма документа и что уходит в промпт."""

import pytest

from app.agent.llm import LLMError, LLMResponseError
from app.agent.modeler import build_model
from tests.agent.support import FailingLLM, FakeLLM, model_payload

TAGGED_DOCUMENT = {
    "variables": [
        {
            "name": "status",
            "type": "enum",
            "values": ["A", "B"],
            "min": None,
            "max": None,
            "description": None,
            "source_reference": None,
        }
    ],
    "initial": {"status": "A"},
    "transitions": [
        {
            "name": "Do",
            "guard": {"op": "eq", "args": [{"op": "var", "name": "status"}, "A"]},
            "effects": [{"variable": "status", "value": "B"}],
            "description": None,
            "source_reference": None,
        }
    ],
    "properties": [
        {
            "id": "P1",
            "type": "forbidden_state",
            "expression": {"op": "eq", "args": [{"op": "var", "name": "status"}, "B"]},
            "description": None,
            "source_reference": None,
        }
    ],
}


async def test_builds_valid_model_and_passes_requirement_text() -> None:
    """Текст требования уходит в сообщение пользователя, ответ становится моделью."""
    client = FakeLLM(model_payload())

    model = await build_model(
        client, requirement_text="Заявку можно исполнить после согласования", attempts=3
    )

    assert [variable.name for variable in model.variables]
    assert [prop.id for prop in model.properties]
    assert "Заявку можно исполнить после согласования" in client.calls[0]["user"]
    assert client.calls[0]["prompt_version"].startswith("modeling-")


async def test_feedback_goes_into_the_user_message() -> None:
    """Замечания к прошлой модели передаются текстом, а не молча теряются."""
    client = FakeLLM(model_payload())

    await build_model(
        client, requirement_text="текст", attempts=1, feedback=["P1 не следует из текста"]
    )

    assert "P1 не следует из текста" in client.calls[0]["user"]


async def test_rejects_document_wrapped_by_model() -> None:
    """Обёртка ``{"model": ...}`` не принимается: схема задаёт документ целиком."""
    client = FakeLLM({"model": model_payload()})

    with pytest.raises(LLMResponseError):
        await build_model(client, requirement_text="текст", attempts=1)


async def test_repairs_invalid_document_on_second_attempt() -> None:
    """Негодный документ не выбрасывается: следующая попытка получает тот же запрос."""
    client = FakeLLM({"variables": []}, model_payload())

    model = await build_model(client, requirement_text="текст", attempts=2)

    assert model.initial
    assert len(client.calls) == 2


async def test_gives_up_after_configured_attempts() -> None:
    """Исчерпание попыток — ошибка с перечнем нарушений, а не пустая модель."""
    client = FakeLLM({"variables": []}, {"variables": []})

    with pytest.raises(LLMResponseError) as raised:
        await build_model(client, requirement_text="текст", attempts=2)

    assert len(client.calls) == 2
    assert raised.value.problems


async def test_provider_failure_is_not_a_bad_document() -> None:
    """Отказ провайдера — это LLMError: переспрашивать модель бессмысленно."""
    client = FailingLLM(1, model_payload())

    with pytest.raises(LLMError, match="провайдер недоступен"):
        await build_model(client, requirement_text="текст", attempts=2)


async def test_tagged_answer_becomes_the_case_form() -> None:
    """В домене остаётся привычный вид кейса: теги и имена полей — только в ответе."""
    client = FakeLLM(TAGGED_DOCUMENT)

    model = await build_model(client, requirement_text="текст", attempts=1)
    document = model.model_dump(mode="json")

    assert document["initial"] == {"status": "A"}
    assert document["transitions"][0]["guard"] == {"eq": [{"var": "status"}, "A"]}
    assert document["transitions"][0]["effects"] == [{"set": ["status", "B"]}]
    assert document["properties"][0]["expression"] == {"eq": [{"var": "status"}, "B"]}
