"""Объяснение контрпримера: цитаты, число шагов и три класса причины."""

import pytest

from app.agent.explainer import explain_result
from app.agent.llm import LLMResponseError
from app.domain.behavioral_model import BehavioralModel
from app.domain.verification import RootCause, VerificationResult, VerificationStatus
from tests.agent.support import FakeLLM, domain_model, explanation_payload, violated_result

REQUIREMENT = (
    "Заявка после согласования может быть исполнена. "
    "Пользователь может отменить заявку до исполнения."
)


def _model() -> BehavioralModel:
    return domain_model()


def _result() -> VerificationResult:
    return VerificationResult.model_validate(violated_result())


async def test_explains_violation_with_scenario_and_root_cause() -> None:
    client = FakeLLM(explanation_payload())

    answered = await explain_result(
        client, requirement_text=REQUIREMENT, model=_model(), result=_result(), attempts=1
    )

    assert answered.explanation.root_cause is RootCause.REQUIREMENT_ERROR
    assert answered.explanation.question
    assert answered.explanation.business_summary.splitlines() == [f"Шаг {n}." for n in range(1, 5)]
    assert [item.quote for item in answered.related_requirements] == [
        "Пользователь может отменить заявку до исполнения."
    ]
    assert "Пользователь может отменить" in client.calls[0]["user"]


async def test_scenario_must_match_trace_length() -> None:
    client = FakeLLM(explanation_payload(steps=3))

    with pytest.raises(LLMResponseError) as raised:
        await explain_result(
            client, requirement_text=REQUIREMENT, model=_model(), result=_result(), attempts=1
        )

    assert "3 предложений" in " ".join(raised.value.problems)
    assert "4 шагов" in " ".join(raised.value.problems)


async def test_rejects_quote_that_is_not_in_requirement() -> None:
    payload = explanation_payload()
    payload["related_requirements"] = [{"paragraph_ref": None, "quote": "Такого текста нет."}]
    client = FakeLLM(payload)

    with pytest.raises(LLMResponseError) as raised:
        await explain_result(
            client, requirement_text=REQUIREMENT, model=_model(), result=_result(), attempts=1
        )

    assert "не встречается в тексте" in " ".join(raised.value.problems)


async def test_rejects_short_quote() -> None:
    """Одна буква не подтверждает связь контрпримера с требованием."""
    payload = explanation_payload()
    payload["related_requirements"] = [{"paragraph_ref": None, "quote": "и"}]
    client = FakeLLM(payload)

    with pytest.raises(LLMResponseError) as raised:
        await explain_result(
            client, requirement_text=REQUIREMENT, model=_model(), result=_result(), attempts=1
        )

    assert "слишком короткая" in " ".join(raised.value.problems)


async def test_rejects_unknown_root_cause() -> None:
    payload = explanation_payload()
    payload["root_cause"] = "BAD_LUCK"
    client = FakeLLM(payload)

    with pytest.raises(LLMResponseError) as raised:
        await explain_result(
            client, requirement_text=REQUIREMENT, model=_model(), result=_result(), attempts=1
        )

    assert "MISSING_RULE" in " ".join(raised.value.problems)


async def test_rejects_empty_question() -> None:
    payload = explanation_payload()
    payload["question"] = "   "
    client = FakeLLM(payload)

    with pytest.raises(LLMResponseError) as raised:
        await explain_result(
            client, requirement_text=REQUIREMENT, model=_model(), result=_result(), attempts=1
        )

    assert "вопрос" in " ".join(raised.value.problems)


async def test_refuses_to_explain_non_violation() -> None:
    result = VerificationResult(
        status=VerificationStatus.PROPERTY_HOLDS, engine="TLC", property_id="P1"
    )

    with pytest.raises(ValueError, match="только при нарушении"):
        await explain_result(
            FakeLLM(),
            requirement_text=REQUIREMENT,
            model=_model(),
            result=result,
            attempts=1,
        )
