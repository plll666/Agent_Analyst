"""Правила объяснения: что обязательно при нарушении и что запрещено без него."""

import pytest

from app.domain.explanation import explanation_errors
from app.domain.verification import (
    RootCause,
    VerificationExplanation,
    VerificationStatus,
)

TERMINAL_WITHOUT_VIOLATION = [
    VerificationStatus.PROPERTY_HOLDS,
    VerificationStatus.TIMEOUT,
    VerificationStatus.STATE_LIMIT_REACHED,
    VerificationStatus.MODEL_INVALID,
    VerificationStatus.ENGINE_ERROR,
    VerificationStatus.AGENT_ERROR,
]


def test_complete_violation_explanation_is_accepted() -> None:
    explanation = VerificationExplanation(
        business_summary="Заявку отменили, но исполнили.",
        hypothesis="В модели нет запрета на исполнение отменённой заявки.",
        question="Должна ли отменённая заявка оставаться исполнимой?",
        root_cause=RootCause.REQUIREMENT_ERROR,
    )

    assert explanation_errors(VerificationStatus.PROPERTY_VIOLATED, explanation) == []


@pytest.mark.parametrize(
    "missing",
    ["business_summary", "hypothesis", "question", "root_cause"],
)
def test_violation_requires_every_part_of_the_answer(missing: str) -> None:
    values: dict[str, object] = {
        "business_summary": "сценарий",
        "hypothesis": "гипотеза",
        "question": "вопрос",
        "root_cause": RootCause.MISSING_RULE,
    }
    values[missing] = None if missing == "root_cause" else "   "

    errors = explanation_errors(
        VerificationStatus.PROPERTY_VIOLATED,
        VerificationExplanation(**values),
    )

    assert errors


@pytest.mark.parametrize("status", TERMINAL_WITHOUT_VIOLATION)
def test_agent_fields_are_forbidden_without_violation(status: VerificationStatus) -> None:
    explanation = VerificationExplanation(
        business_summary="текст",
        hypothesis="гипотеза",
        question="вопрос",
        root_cause=RootCause.AGENT_ERROR,
    )

    errors = explanation_errors(status, explanation)

    assert len(errors) == 3


def test_empty_summary_is_rejected_on_terminal_status() -> None:
    errors = explanation_errors(
        VerificationStatus.PROPERTY_HOLDS, VerificationExplanation(business_summary="  ")
    )

    assert errors


def test_pending_allows_empty_summary() -> None:
    assert (
        explanation_errors(VerificationStatus.PENDING, VerificationExplanation(business_summary=""))
        == []
    )


def test_agent_error_explains_that_the_model_was_not_built() -> None:
    """Ошибка агента — не результат проверки, но объяснить её пользователю надо."""
    explanation = VerificationExplanation(
        business_summary="Агент не смог построить модель по этому требованию."
    )

    assert explanation_errors(VerificationStatus.AGENT_ERROR, explanation) == []
