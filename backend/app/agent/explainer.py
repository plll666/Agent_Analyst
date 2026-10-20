"""Объяснение контрпримера на языке требований.

Модель получает только факт от движка: свойство и трассу. Она не пересчитывает
перебор и не правит модель — на выходе только сценарий, гипотеза, класс причины и
вопрос. Цитаты из требования проверяются на вхождение в исходный текст: ссылка на
фразу, которой в задании нет, — такая же выдумка, как выдуманный шаг трассы.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.agent.llm import LLMClient, request_validated
from app.agent.prompts import EXPLANATION_PROMPT_VERSION, EXPLANATION_SYSTEM, explanation_user
from app.domain.behavioral_model import BehavioralModel
from app.domain.explanation import explanation_errors
from app.domain.verification import (
    RelatedRequirement,
    RootCause,
    VerificationExplanation,
    VerificationResult,
    VerificationStatus,
)


@dataclass(frozen=True, slots=True)
class AgentExplanation:
    """Объяснение агента вместе со ссылками на исходный текст."""

    explanation: VerificationExplanation
    related_requirements: tuple[RelatedRequirement, ...]


async def explain_result(
    client: LLMClient,
    *,
    requirement_text: str,
    model: BehavioralModel,
    result: VerificationResult,
    attempts: int,
) -> AgentExplanation:
    """Объяснить нарушение свойства по трассе контрпримера.

    Args:
        client: Клиент LLM.
        requirement_text: Текст, по которому построена модель.
        model: Модель, которую проверял движок.
        result: Результат проверки со статусом ``PROPERTY_VIOLATED``.
        attempts: Сколько попыток дать модели на исправление ответа.

    Returns:
        Сценарий, гипотеза, класс причины, вопрос и цитаты из требования.

    Raises:
        ValueError: результат не является нарушением — объяснять нечего.
        LLMResponseError: пригодный ответ не получился за отведённые попытки.
        LLMError: провайдер недоступен или вернул не JSON.
    """
    if result.status is not VerificationStatus.PROPERTY_VIOLATED:
        raise ValueError(f"объяснять контрпример можно только при нарушении, а не {result.status}")
    user = explanation_user(
        requirement_text,
        json.dumps(model.model_dump(mode="json"), ensure_ascii=False, indent=2),
        _trace_json(result),
    )
    return await request_validated(
        client,
        system=EXPLANATION_SYSTEM,
        user=user,
        prompt_version=EXPLANATION_PROMPT_VERSION,
        attempts=attempts,
        parse=lambda payload: _parse_explanation(payload, requirement_text, result),
    )


def _trace_json(result: VerificationResult) -> str:
    """Сериализовать только факт нарушения: свойство и шаги."""
    counterexample = (
        result.counterexample.model_dump(mode="json") if result.counterexample is not None else None
    )
    payload = {"property_id": result.property_id, "counterexample": counterexample}
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _parse_explanation(
    payload: Mapping[str, Any], requirement_text: str, result: VerificationResult
) -> AgentExplanation:
    """Проверить ответ модели и собрать доменное объяснение."""
    steps = _scenario(payload)
    expected_steps = len(result.counterexample.steps) if result.counterexample is not None else 0
    if expected_steps and len(steps) != expected_steps:
        raise ValueError(
            f"в scenario {len(steps)} предложений, а в трассе {expected_steps} шагов: "
            "опиши ровно по одному предложению на шаг"
        )

    explanation = VerificationExplanation(
        business_summary="\n".join(steps),
        hypothesis=_required_text(payload, "hypothesis"),
        question=_required_text(payload, "question"),
        root_cause=_root_cause(payload),
    )
    errors = explanation_errors(VerificationStatus.PROPERTY_VIOLATED, explanation)
    if errors:
        raise ValueError("; ".join(errors))
    return AgentExplanation(
        explanation=explanation,
        related_requirements=_related(payload, requirement_text),
    )


def _scenario(payload: Mapping[str, Any]) -> list[str]:
    raw = payload.get("scenario")
    if not isinstance(raw, list):
        raise ValueError("scenario должен быть непустым списком предложений")
    steps = [item.strip() for item in raw if isinstance(item, str) and item.strip()]
    if not steps:
        raise ValueError("scenario пуст: опиши шаги контрпримера")
    return steps


def _required_text(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} обязателен и не может быть пустым")
    return value.strip()


def _root_cause(payload: Mapping[str, Any]) -> RootCause:
    value = payload.get("root_cause")
    if not isinstance(value, str):
        raise ValueError("root_cause обязателен: одна из трёх причин")
    try:
        return RootCause(value)
    except ValueError as error:
        allowed = ", ".join(str(cause) for cause in RootCause)
        raise ValueError(f"неизвестный root_cause {value!r}; допустимые: {allowed}") from error


def _related(payload: Mapping[str, Any], requirement_text: str) -> tuple[RelatedRequirement, ...]:
    raw = payload.get("related_requirements", [])
    if not isinstance(raw, list):
        raise ValueError("related_requirements должен быть списком")
    normalized_text = _normalize(requirement_text)
    related: list[RelatedRequirement] = []
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise ValueError(f"related_requirements[{index}] должен быть объектом")
        quote = item.get("quote")
        if quote is None:
            continue
        if not isinstance(quote, str) or not quote.strip():
            raise ValueError(f"related_requirements[{index}].quote пуст")
        if _normalize(quote) not in normalized_text:
            raise ValueError(
                f"цитата {quote!r} не встречается в тексте требования: "
                "приводи только дословные фрагменты"
            )
        paragraph_ref = item.get("paragraph_ref")
        if paragraph_ref is not None and not isinstance(paragraph_ref, str):
            raise ValueError(f"related_requirements[{index}].paragraph_ref должен быть строкой")
        related.append(RelatedRequirement(paragraph_ref=paragraph_ref, quote=quote.strip()))
    return tuple(related)


def _normalize(text: str) -> str:
    """Свести пробелы, чтобы цитата не ломалась на переносах строк."""
    return " ".join(text.split())
