"""Качество объяснения: только факты трассы и язык бизнеса.

Объяснение читает автор требования. Поэтому проверяются два запрета: нельзя
называть событие, которого нет в трассе, и нельзя объяснять через TLA+, TLC,
SANY и инварианты. Отдельно проверяется, что класс причины ``MISSING_RULE``
не подменяется: если текст требования молчит о случае, так и остаётся.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from app.agent.explainer import explain_result
from app.agent.llm import LLMResponseError
from app.domain.behavioral_model import BehavioralModel
from app.domain.verification import RootCause, VerificationResult
from tests.agent.support import FakeLLM, domain_model, explanation_payload, violated_result
from tests.domain.case_examples import case_model

REQUIREMENT = (
    "Заявка после согласования может быть исполнена. "
    "Пользователь может отменить заявку до исполнения."
)


def _result(steps: int | None = None) -> VerificationResult:
    document: dict[str, Any] = deepcopy(violated_result())
    if steps is not None:
        document["counterexample"]["steps"] = document["counterexample"]["steps"][:steps]
    return VerificationResult.model_validate(document)


def _case_model() -> BehavioralModel:
    return BehavioralModel.model_validate(case_model())


async def _explain(model: BehavioralModel, payload: dict[str, Any], *, steps: int | None) -> None:
    await explain_result(
        FakeLLM(payload),
        requirement_text=REQUIREMENT,
        model=model,
        result=_result(steps),
        attempts=1,
    )


async def test_rejects_transition_that_is_not_in_the_trace() -> None:
    """Cancel есть в модели, но в короткой трассе его нет — это выдумка."""
    payload = explanation_payload(steps=2)
    payload["scenario"][1] = "Событие Cancel отменяет заявку."

    with pytest.raises(LLMResponseError) as raised:
        await _explain(_case_model(), payload, steps=2)

    problems = " ".join(raised.value.problems)
    assert "Cancel" in problems
    assert "нет в трассе" in problems


async def test_allows_transition_that_is_in_the_trace() -> None:
    """Тот же переход в полной трассе называется по делу и не отвергается."""
    payload = explanation_payload()
    payload["scenario"][1] = "Событие Approve переводит заявку в согласованное состояние."

    await _explain(_case_model(), payload, steps=None)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("hypothesis", "Инвариант нарушен: TLC нашёл контрпример."),
        ("hypothesis", "TLA+ описание содержит ошибку перехода."),
        ("hypothesis", "SANY не разобрал спецификацию."),
        ("question", "Что делать с дедлоком после отмены?"),
        ("hypothesis", "Deadlock возникает после исполнения заявки."),
    ],
)
async def test_rejects_model_checker_jargon(field: str, value: str) -> None:
    payload = explanation_payload()
    payload[field] = value

    with pytest.raises(LLMResponseError) as raised:
        await _explain(domain_model(), payload, steps=None)

    assert "технический термин" in " ".join(raised.value.problems)


async def test_rejects_jargon_in_the_scenario() -> None:
    payload = explanation_payload()
    payload["scenario"][2] = "TLC проверяет инвариант на этом шаге."

    with pytest.raises(LLMResponseError) as raised:
        await _explain(domain_model(), payload, steps=None)

    assert "scenario" in " ".join(raised.value.problems)


async def test_business_wording_is_not_mistaken_for_jargon() -> None:
    """Русское слово «отлаженный» не содержит латинского TLA."""
    payload = explanation_payload()
    payload["hypothesis"] = "Отлаженный процесс согласования не учитывает отмену после исполнения."

    await _explain(domain_model(), payload, steps=None)


async def test_missing_rule_root_cause_is_preserved() -> None:
    """Если требования молчат о случае, причина остаётся MISSING_RULE."""
    payload = explanation_payload()
    payload["root_cause"] = "MISSING_RULE"
    payload["hypothesis"] = (
        "В тексте требования не сказано, можно ли исполнять заявку после отмены."
    )
    payload["question"] = "Нужно ли запретить исполнение отменённой заявки?"

    answered = await explain_result(
        FakeLLM(payload),
        requirement_text=REQUIREMENT,
        model=domain_model(),
        result=_result(),
        attempts=1,
    )

    assert answered.explanation.root_cause is RootCause.MISSING_RULE
    assert answered.explanation.question == "Нужно ли запретить исполнение отменённой заявки?"
