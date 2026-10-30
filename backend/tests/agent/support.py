"""Тесты агента на подставном клиенте: без сети и без ключа."""

import json
from collections.abc import Mapping
from copy import deepcopy
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.agent.llm import LLMSettings
from app.domain.behavioral_model import BehavioralModel
from tests.domain.case_examples import CASE_RESULT_VIOLATED, contract_model_fixed

ModelT = TypeVar("ModelT", bound=BaseModel)


class FakeLLM:
    """Клиент, который отдаёт заранее заготовленные ответы и запоминает запросы.

    Ответ проверяется той же моделью, что и у настоящего клиента, поэтому
    негодный поле не проходит молча: тест падает там же, где упал бы Instructor.
    """

    def __init__(self, *payloads: Mapping[str, Any]) -> None:
        self._payloads = [dict(payload) for payload in payloads]
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    async def parse(
        self,
        response_model: type[ModelT],
        *,
        system: str,
        user: str,
        prompt_version: str,
        attempts: int,
        context: Mapping[str, Any] | None = None,
        reasoning: bool | None = None,
    ) -> ModelT:
        problems: list[str] = []
        for _ in range(max(1, attempts)):
            self.calls.append(
                {
                    "system": system,
                    "user": user,
                    "prompt_version": prompt_version,
                    "reasoning": reasoning,
                    "attempts": attempts,
                    "context": context,
                }
            )
            if not self._payloads:
                raise AssertionError("лишний вызов LLM")
            payload = self._payloads.pop(0)
            try:
                return response_model.model_validate(
                    payload, context=dict(context) if context else None
                )
            except ValidationError as error:
                problems.append(str(error))
        from app.agent.llm import LLMResponseError

        raise LLMResponseError(f"LLM не вернула пригодный ответ за {attempts} попыток", problems)

    async def aclose(self) -> None:
        self.closed = True


class FailingLLM(FakeLLM):
    """Клиент, который падает заданное число раз, а потом отвечает."""

    def __init__(self, failures: int, *payloads: Mapping[str, Any]) -> None:
        super().__init__(*payloads)
        self._failures = failures

    async def parse(
        self,
        response_model: type[ModelT],
        *,
        system: str,
        user: str,
        prompt_version: str,
        attempts: int,
        context: Mapping[str, Any] | None = None,
        reasoning: bool | None = None,
    ) -> ModelT:
        from app.agent.llm import LLMError

        _ = reasoning

        if self._failures:
            self._failures -= 1
            raise LLMError("провайдер недоступен")
        return await super().parse(
            response_model,
            system=system,
            user=user,
            prompt_version=prompt_version,
            attempts=attempts,
            context=context,
        )


def model_payload() -> dict[str, Any]:
    """Валидный документ модели в том виде, в котором его отдаёт модель."""
    return to_wire_model(contract_model_fixed())


def cited_payload(document: Mapping[str, Any], quote: str) -> dict[str, Any]:
    """Документ в форме ответа, у которого каждое правило подкреплено цитатой.

    Без цитат ворота не пропустят модель: правило без ссылки на текст считается
    придуманным агентом.
    """
    prepared = deepcopy(dict(document))
    for transition in prepared["transitions"]:
        transition["source_reference"] = quote
    for prop in prepared["properties"]:
        prop["source_reference"] = quote
    return to_wire_model(prepared)


def domain_model() -> BehavioralModel:
    """Модель в доменном виде — как её видит движок."""
    return BehavioralModel.model_validate(contract_model_fixed())


def to_wire_model(document: Mapping[str, Any]) -> dict[str, Any]:
    """Перевести документ кейса в форму ответа модели.

    В кейсе выражения записаны как ``{"var": "status"}``, а модель отвечает
    выражениями с тегом ``op`` и присваиваниями по именам. ``initial`` в обоих
    случаях — объект. Разница только в записи, и перевод показывает её явно.
    """
    return {
        "variables": [
            {
                "name": variable["name"],
                "type": variable["type"],
                "values": variable.get("values"),
                "min": variable.get("min"),
                "max": variable.get("max"),
                "description": variable.get("description"),
                "source_reference": variable.get("source_reference"),
            }
            for variable in document["variables"]
        ],
        "initial": dict(document["initial"]),
        "transitions": [
            {
                "name": transition["name"],
                "guard": _expression_to_wire(transition["guard"]),
                "effects": [
                    {"variable": effect["set"][0], "value": effect["set"][1]}
                    for effect in transition["effects"]
                ],
                "description": transition.get("description"),
                "source_reference": transition.get("source_reference"),
            }
            for transition in document["transitions"]
        ],
        "properties": [
            {
                "id": prop["id"],
                "type": prop["type"],
                "expression": (
                    _expression_to_wire(prop["expression"]) if prop.get("expression") else None
                ),
                "description": prop.get("description"),
                "source_reference": prop.get("source_reference"),
            }
            for prop in document["properties"]
        ],
    }


def _expression_to_wire(expression: Mapping[str, Any]) -> dict[str, Any]:
    """Выражение кейса → выражение с тегом ``op``."""
    if "var" in expression:
        return {"op": "var", "name": expression["var"]}
    if "and" in expression:
        return {"op": "and", "args": [_expression_to_wire(arg) for arg in expression["and"]]}
    if "eq" in expression:
        return {"op": "eq", "args": [_operand_to_wire(arg) for arg in expression["eq"]]}
    if "in" in expression:
        value, members = expression["in"]
        return {"op": "in", "value": _operand_to_wire(value), "members": list(members)}
    raise ValueError(f"неизвестное выражение: {expression}")


def _operand_to_wire(operand: Any) -> Any:
    """Операнд — это выражение или скаляр."""
    if isinstance(operand, Mapping):
        return _expression_to_wire(operand)
    return operand


def violated_result() -> dict[str, Any]:
    """Результат с контрпримером из четырёх шагов."""
    return dict(CASE_RESULT_VIOLATED)


def explanation_payload(steps: int = 4) -> dict[str, Any]:
    """Ответ объяснения, согласованный с трассой из четырёх шагов."""
    return {
        "scenario": [f"Шаг {index}." for index in range(1, steps + 1)],
        "hypothesis": "В модели нет условия, запрещающего исполнение отменённой заявки.",
        "root_cause": "REQUIREMENT_ERROR",
        "question": "Должна ли отменённая заявка оставаться исполнимой?",
        "related_requirements": [
            {"paragraph_ref": None, "quote": "Пользователь может отменить заявку до исполнения."}
        ],
    }


def settings(**overrides: Any) -> LLMSettings:
    """Настройки провайдера для теста."""
    values: dict[str, Any] = {
        "base_url": "https://llm.example/v1",
        "api_key": "key",
        "model": "test-model",
        "timeout_seconds": 5.0,
        "max_attempts": 3,
    }
    values.update(overrides)
    return LLMSettings(**values)


def dump(value: Mapping[str, Any]) -> str:
    """Компактный JSON для сообщений об ошибке."""
    return json.dumps(value, ensure_ascii=False)
