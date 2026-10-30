"""Объяснение контрпримера на языке требований.

Модель получает только факт от движка: свойство и трассу. Она не пересчитывает
перебор и не правит модель — на выходе только сценарий, гипотеза, класс причины и
вопрос. Цитаты из требования проверяются на вхождение в исходный текст: ссылка на
фразу, которой в задании нет, — такая же выдумка, как выдуманный шаг трассы.

Проверки живут в модели ответа (:class:`app.agent.schema_models.WireExplanation`),
поэтому негодный ответ не отбрасывается молча: Instructor переспрашивает модель с
текстом нарушения.
"""

import json
from dataclasses import dataclass

from app.agent.llm import LLMClient
from app.agent.prompts import EXPLANATION_PROMPT_VERSION, EXPLANATION_SYSTEM, explanation_user
from app.agent.schema_models import WireExplanation
from app.domain.behavioral_model import BehavioralModel
from app.domain.verification import (
    RelatedRequirement,
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
    reasoning: bool | None = None,
) -> AgentExplanation:
    """Объяснить нарушение свойства по трассе контрпримера.

    Args:
        client: Клиент LLM.
        requirement_text: Текст, по которому построена модель.
        model: Модель, которую проверял движок.
        result: Результат проверки со статусом ``PROPERTY_VIOLATED``.
        attempts: Сколько попыток дать модели на исправление ответа.
        reasoning: Рассуждать ли модели до ответа; ``None`` — поведение
            провайдера по умолчанию.

    Returns:
        Сценарий, гипотеза, класс причины, вопрос и цитаты из требования.

    Raises:
        ValueError: результат не является нарушением — объяснять нечего.
        LLMResponseError: пригодный ответ не получился за отведённые попытки.
        LLMError: провайдер недоступен или отказал в запросе.
    """
    if result.status is not VerificationStatus.PROPERTY_VIOLATED:
        raise ValueError(f"объяснять контрпример можно только при нарушении, а не {result.status}")
    wire = await client.parse(
        WireExplanation,
        system=EXPLANATION_SYSTEM,
        user=explanation_user(
            requirement_text,
            json.dumps(model.model_dump(mode="json"), ensure_ascii=False, indent=2),
            _trace_json(result),
        ),
        prompt_version=EXPLANATION_PROMPT_VERSION,
        attempts=attempts,
        context={"requirement_text": requirement_text, "steps": _trace_steps(result)},
        reasoning=reasoning,
    )
    explanation, related = wire.to_explanation()
    return AgentExplanation(explanation=explanation, related_requirements=related)


def _trace_json(result: VerificationResult) -> str:
    """Сериализовать только факт нарушения: свойство и шаги."""
    counterexample = (
        result.counterexample.model_dump(mode="json") if result.counterexample is not None else None
    )
    payload = {"property_id": result.property_id, "counterexample": counterexample}
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _trace_steps(result: VerificationResult) -> int:
    """Сколько шагов в трассе: по одному предложению сценария на шаг."""
    return len(result.counterexample.steps) if result.counterexample is not None else 0
