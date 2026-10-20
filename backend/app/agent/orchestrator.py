"""Цикл агента: от текста требования к результату проверки.

Пока пользователь не ответил на вопрос, агент ведёт цикл сам:

1. Модель строится по тексту требования.
2. Модель проходит ворота: каждое правило подкреплено цитатой из текста. Не
   прошла — агент перестраивает модель, получая список замечаний.
3. Свойства проверяет детерминированный движок. Сам агент состояния не
   перебирает и по шагам трассы не ходит.
4. Нарушение разбирается на языке требований: сценарий, гипотеза, класс причины
   и вопрос пользователю.
5. Решение: спросить пользователя или остановиться с честным результатом.

Модуль ничего не знает про БД и про очередь: на входе текст требования, клиент
LLM и способ проверить одно свойство; на выходе — результат, объяснение и
решение. Запись в базу делает вызывающая сторона.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from pydantic import ValidationError

from app.agent import self_check
from app.agent.explainer import explain_result
from app.agent.llm import LLMClient, LLMError
from app.agent.modeler import build_model
from app.domain.behavioral_model import BehavioralModel, Property
from app.domain.decision import AnalysisDecision, decide
from app.domain.explanation import summary_for
from app.domain.verdict import combine
from app.domain.verification import (
    VerificationExplanation,
    VerificationResult,
    VerificationStatus,
)

logger = logging.getLogger(__name__)

CheckProperty = Callable[[BehavioralModel, Property], Awaitable[VerificationResult]]

ENGINE_WHEN_AGENT_FAILED = "AGENT"


@dataclass(frozen=True, slots=True)
class CycleLimits:
    """Границы одной итерации.

    Attributes:
        build_attempts: Сколько попыток у модели на валидный документ.
        max_rebuilds: Сколько раз агент перестраивает модель после замечаний ворот.
        explanation_attempts: Сколько попыток у модели на объяснение нарушения.
    """

    build_attempts: int = 3
    max_rebuilds: int = 2
    explanation_attempts: int = 3


@dataclass(frozen=True, slots=True)
class Iteration:
    """Итог одной итерации агента.

    Attributes:
        status: Статус итерации.
        model: Построенная модель; ``None``, если агент не смог её построить.
        result: Результат проверки; ``None``, если до движка дело не дошло.
        explanation: Объяснение на языке требований.
        decision: Спросить пользователя или остановиться.
        gate_problems: Замечания ворот, из-за которых модель перестраивалась.
        rebuilds: Сколько раз модель перестраивалась.
    """

    status: VerificationStatus
    model: BehavioralModel | None
    result: VerificationResult | None
    explanation: VerificationExplanation
    decision: AnalysisDecision
    gate_problems: tuple[str, ...] = ()
    rebuilds: int = 0


async def run_iteration(
    *,
    client: LLMClient,
    requirement_text: str,
    check_property: CheckProperty,
    limits: CycleLimits | None = None,
) -> Iteration:
    """Провести одну итерацию агента: модель, проверка, объяснение, решение.

    Args:
        client: Клиент LLM.
        requirement_text: Текст требования.
        check_property: Как проверить одно свойство движком.
        limits: Границы итерации.

    Returns:
        Итог итерации.
    """
    bounds = limits or CycleLimits()
    model, problems, rebuilds = await _build_through_gate(
        client,
        requirement_text=requirement_text,
        limits=bounds,
    )
    if model is None:
        return _agent_failed(problems, rebuilds)

    results = [await check_property(model, prop) for prop in model.properties]
    result = combine(results)
    result, explanation = await _explain(
        client,
        requirement_text=requirement_text,
        model=model,
        result=result,
        limits=bounds,
    )
    return Iteration(
        status=result.status,
        model=model,
        result=result,
        explanation=explanation,
        decision=decide(result.status),
        gate_problems=tuple(problems),
        rebuilds=rebuilds,
    )


async def _build_through_gate(
    client: LLMClient,
    *,
    requirement_text: str,
    limits: CycleLimits,
) -> tuple[BehavioralModel | None, list[str], int]:
    """Построить модель и провести её через ворота.

    Модель строится заново, пока ворота её не пропустят. Если замечания
    повторились, перестраивать дальше бессмысленно — цикл останавливается.

    Returns:
        Модель (или ``None``), замечания и число перестроений.
    """
    problems: list[str] = []
    rebuilds = 0
    for attempt in range(limits.max_rebuilds + 1):
        try:
            model = await build_model(
                client,
                requirement_text=requirement_text,
                attempts=limits.build_attempts if attempt == 0 else 1,
                feedback=problems,
            )
        except (LLMError, ValidationError) as error:
            return None, [*problems, str(error)], rebuilds
        gate = self_check.check(model, requirement_text)
        if not gate:
            return model, problems, rebuilds
        if gate == problems:
            logger.warning("ворота вернули те же замечания второй раз подряд: %s", "; ".join(gate))
            return None, gate, rebuilds
        problems = gate
        rebuilds += 1
    return None, problems, rebuilds


async def _explain(
    client: LLMClient,
    *,
    requirement_text: str,
    model: BehavioralModel,
    result: VerificationResult,
    limits: CycleLimits,
) -> tuple[VerificationResult, VerificationExplanation]:
    """Объяснить нарушение на языке требований либо оставить честный шаблон.

    Модель зовётся только при нарушении: у остальных статусов сценария нет, а
    пересказ отказа грозит выдать его за успех.
    """
    fallback = VerificationExplanation(business_summary=summary_for(result.status))
    if result.status is not VerificationStatus.PROPERTY_VIOLATED:
        return result, fallback
    try:
        answered = await explain_result(
            client,
            requirement_text=requirement_text,
            model=model,
            result=result,
            attempts=limits.explanation_attempts,
        )
    except (LLMError, ValidationError) as error:
        logger.warning("объяснение контрпримера не получено, остаётся шаблон: %s", error)
        return result, fallback
    enriched = result.model_copy(update={"related_requirements": answered.related_requirements})
    return enriched, answered.explanation


def _agent_failed(problems: Sequence[str], rebuilds: int) -> Iteration:
    """Итерация, на которой агент не смог построить пригодную модель."""
    detail = "; ".join(problems) or "агент не вернул пригодную модель"
    result = VerificationResult(
        status=VerificationStatus.AGENT_ERROR,
        engine=ENGINE_WHEN_AGENT_FAILED,
        error_detail=detail,
    )
    return Iteration(
        status=VerificationStatus.AGENT_ERROR,
        model=None,
        result=result,
        explanation=VerificationExplanation(
            business_summary=summary_for(VerificationStatus.AGENT_ERROR)
        ),
        decision=AnalysisDecision.STOP,
        gate_problems=tuple(problems),
        rebuilds=rebuilds,
    )
