"""Сведение прогонов по свойствам в один результат.

Правило сводимости — место, где ошибка превращается в ложный успех, поэтому
каждый случай зафиксирован отдельным тестом.
"""

import pytest

from app.domain.verdict import combine
from app.domain.verification import (
    Counterexample,
    CounterexampleStep,
    Statistics,
    VerificationResult,
)
from app.domain.verification import VerificationStatus as Status


def _holds(property_id: str = "P1") -> VerificationResult:
    return VerificationResult(
        status=Status.PROPERTY_HOLDS,
        property_id=property_id,
        engine="TLC",
        statistics=Statistics(states_generated=10, distinct_states=5, depth=3),
        duration_ms=100,
    )


def _violated(property_id: str = "P1") -> VerificationResult:
    return VerificationResult(
        status=Status.PROPERTY_VIOLATED,
        property_id=property_id,
        engine="TLC",
        counterexample=Counterexample(
            steps=(
                CounterexampleStep(number=0, state={"status": "Created"}),
                CounterexampleStep(number=1, transition="Approve", state={"status": "Approved"}),
            )
        ),
    )


def _failure(status: Status, property_id: str = "P1") -> VerificationResult:
    return VerificationResult(
        status=status, property_id=property_id, engine="TLC", error_detail="подробности"
    )


def test_single_success_passes_through() -> None:
    """Единственный успешный прогон остаётся успешным."""
    assert combine([_holds()]).status is Status.PROPERTY_HOLDS


def test_violation_wins_over_timeout_of_another_property() -> None:
    """Найденное нарушение нельзя молча спрятать за таймаут соседнего свойства."""
    combined = combine([_failure(Status.TIMEOUT, "P2"), _violated("P1")])

    assert combined.status is Status.PROPERTY_VIOLATED
    assert combined.property_id == "P1"
    assert combined.counterexample is not None


def test_timeout_is_never_reported_as_holds() -> None:
    """Свойство, которое не дочиталось, не проверено — успеха быть не может."""
    combined = combine([_holds("P1"), _failure(Status.TIMEOUT, "P2")])

    assert combined.status is Status.TIMEOUT


def test_state_limit_is_never_reported_as_holds() -> None:
    """Исчерпанный лимит состояний — тоже отсутствие результата."""
    combined = combine([_holds("P1"), _failure(Status.STATE_LIMIT_REACHED, "P2")])

    assert combined.status is Status.STATE_LIMIT_REACHED


def test_failure_precedence_does_not_depend_on_property_order() -> None:
    """Порядок свойств в модели не должен менять итоговый статус."""
    first = combine([_failure(Status.TIMEOUT, "P1"), _failure(Status.ENGINE_ERROR, "P2")])
    second = combine([_failure(Status.ENGINE_ERROR, "P2"), _failure(Status.TIMEOUT, "P1")])

    assert first.status is second.status is Status.TIMEOUT


def test_all_successes_sum_their_statistics() -> None:
    """Каждое свойство перебиралось отдельно, поэтому счётчики складываются."""
    combined = combine([_holds("P1"), _holds("P2")])

    assert combined.status is Status.PROPERTY_HOLDS
    assert combined.statistics is not None
    assert combined.statistics.states_generated == 20
    assert combined.statistics.distinct_states == 10
    assert combined.statistics.depth == 3


def test_success_names_every_property_it_covered() -> None:
    """Успех относится ко всем проверенным свойствам, а не к одному."""
    combined = combine([_holds("P1"), _holds("P2")])

    assert combined.property_id == "P1, P2"


def test_success_sums_durations() -> None:
    """Общее время прогона — сумма времён отдельных проверок."""
    combined = combine([_holds("P1"), _holds("P2")])

    assert combined.duration_ms == 200


def test_violation_carries_the_counterexample_of_the_offending_property() -> None:
    """Контрпример в результате — тот, который нашла конкретная проверка."""
    combined = combine([_holds("P1"), _violated("P2")])

    assert combined.property_id == "P2"
    assert combined.counterexample is not None
    assert combined.counterexample.steps[1].transition == "Approve"


def test_rejects_an_empty_run() -> None:
    """Пустой набор — не «всё хорошо», а отсутствие проверки."""
    with pytest.raises(ValueError, match="ни одно свойство не проверено"):
        combine([])
