"""Тесты агента на подставном клиенте: без сети и без ключа."""

import json
from collections.abc import Mapping
from typing import Any

from app.agent.llm import LLMSettings
from tests.domain.case_examples import CASE_RESULT_VIOLATED, contract_model_fixed


class FakeLLM:
    """Клиент, который отдаёт заранее заготовленные ответы и запоминает запросы."""

    def __init__(self, *payloads: Mapping[str, Any]) -> None:
        self._payloads = [dict(payload) for payload in payloads]
        self.calls: list[dict[str, str]] = []
        self.closed = False

    async def complete_json(self, *, system: str, user: str, prompt_version: str) -> dict[str, Any]:
        self.calls.append({"system": system, "user": user, "prompt_version": prompt_version})
        if not self._payloads:
            raise AssertionError("лишний вызов LLM")
        return self._payloads.pop(0)

    async def aclose(self) -> None:
        self.closed = True


class FailingLLM(FakeLLM):
    """Клиент, который падает заданное число раз, а потом отвечает."""

    def __init__(self, failures: int, *payloads: Mapping[str, Any]) -> None:
        super().__init__(*payloads)
        self._failures = failures

    async def complete_json(self, *, system: str, user: str, prompt_version: str) -> dict[str, Any]:
        from app.agent.llm import LLMError

        if self._failures:
            self._failures -= 1
            raise LLMError("провайдер недоступен")
        return await super().complete_json(system=system, user=user, prompt_version=prompt_version)


def model_payload() -> dict[str, Any]:
    """Валидный документ модели из контрактных примеров."""
    return contract_model_fixed()


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
