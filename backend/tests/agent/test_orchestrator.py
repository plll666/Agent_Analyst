"""Цикл агента: модель, ворота, движок, объяснение и решение."""

from typing import Any

from app.agent.orchestrator import CycleLimits, Iteration, run_iteration
from app.domain.behavioral_model import BehavioralModel, Property
from app.domain.decision import AnalysisDecision
from app.domain.verification import (
    RootCause,
    VerificationResult,
    VerificationStatus,
)
from tests.agent.support import FailingLLM, FakeLLM, explanation_payload, to_wire_model
from tests.domain.case_examples import CASE_RESULT_VIOLATED

REQUIREMENT = (
    "Заявка после согласования может быть исполнена. "
    "Пользователь может отменить заявку до исполнения."
)
QUOTE = "Заявка после согласования может быть исполнена"

LIMITS = CycleLimits(build_attempts=1, max_rebuilds=2, explanation_attempts=1)


def _cited_model() -> dict[str, Any]:
    """Модель, у которой каждое правило подкреплено цитатой из текста."""
    return {
        "variables": [
            {
                "name": "status",
                "type": "enum",
                "values": ["Created", "Approved", "Cancelled", "Executed"],
                "source_reference": QUOTE,
            },
            {"name": "approved", "type": "boolean", "source_reference": QUOTE},
        ],
        "initial": {"status": "Created", "approved": False},
        "transitions": [
            {
                "name": "Approve",
                "guard": {"eq": [{"var": "status"}, "Created"]},
                "effects": [
                    {"set": ["status", "Approved"]},
                    {"set": ["approved", True]},
                ],
                "source_reference": QUOTE,
            }
        ],
        "properties": [
            {
                "id": "P1",
                "type": "forbidden_state",
                "expression": {"eq": [{"var": "approved"}, True]},
                "source_reference": QUOTE,
            }
        ],
    }


def _uncited_model() -> dict[str, Any]:
    """Та же модель, но без ссылок на текст: правила ничем не подкреплены."""
    document = _cited_model()
    document["transitions"][0].pop("source_reference")
    document["properties"][0].pop("source_reference")
    return document


async def _violated(_model: BehavioralModel, _prop: Property) -> VerificationResult:
    """Движок нашёл нарушение."""
    return VerificationResult.model_validate(CASE_RESULT_VIOLATED)


async def _holds(_model: BehavioralModel, _prop: Property) -> VerificationResult:
    """Движок не нашёл нарушений."""
    return VerificationResult.model_validate(
        {
            "status": "PROPERTY_HOLDS",
            "property_id": "P1",
            "engine": "TLC",
            "statistics": {"states_generated": 12, "distinct_states": 4, "depth": 3},
        }
    )


async def _iterate(client: Any, check_property: Any = _violated) -> Iteration:
    return await run_iteration(
        client=client,
        requirement_text=REQUIREMENT,
        check_property=check_property,
        limits=LIMITS,
    )


async def test_violation_ends_with_a_question_for_the_user() -> None:
    """Нарушение — единственный повод спросить: пользователю есть что уточнять."""
    client = FakeLLM(to_wire_model(_cited_model()), explanation_payload())

    iteration = await _iterate(client)

    assert iteration.status is VerificationStatus.PROPERTY_VIOLATED
    assert iteration.decision is AnalysisDecision.ASK
    assert iteration.explanation.question
    assert iteration.explanation.hypothesis
    assert iteration.explanation.root_cause is RootCause.REQUIREMENT_ERROR
    assert iteration.result is not None
    assert iteration.result.related_requirements


async def test_holds_stops_without_asking_the_model_for_an_explanation() -> None:
    """Нет нарушения — нет сценария, и модель про пересказ не зовётся."""
    client = FakeLLM(to_wire_model(_cited_model()))

    iteration = await _iterate(client, _holds)

    assert iteration.status is VerificationStatus.PROPERTY_HOLDS
    assert iteration.decision is AnalysisDecision.STOP
    assert iteration.explanation.hypothesis is None
    assert iteration.explanation.question is None
    assert len(client.calls) == 1


async def test_gate_rejection_rebuilds_the_model() -> None:
    """Модель без цитат не идёт в движок: агент перестраивает её."""
    client = FakeLLM(
        to_wire_model(_uncited_model()), to_wire_model(_cited_model()), explanation_payload()
    )

    iteration = await _iterate(client)

    assert iteration.rebuilds == 1
    assert iteration.gate_problems
    assert iteration.status is VerificationStatus.PROPERTY_VIOLATED


async def test_gate_that_never_passes_ends_the_iteration_with_agent_error() -> None:
    """Ворота не пропускают — итерация честно останавливается, а не крутится."""
    client = FakeLLM(
        to_wire_model(_uncited_model()),
        to_wire_model(_uncited_model()),
        to_wire_model(_uncited_model()),
    )

    iteration = await _iterate(client)

    assert iteration.status is VerificationStatus.AGENT_ERROR
    assert iteration.model is None
    assert iteration.decision is AnalysisDecision.STOP
    assert iteration.result is not None
    assert iteration.result.error_detail
    assert iteration.explanation.business_summary


async def test_unavailable_provider_ends_the_iteration_with_agent_error() -> None:
    """Нет провайдера — нет модели, и это видно по статусу, а не по молчанию."""
    client = FailingLLM(failures=5)

    iteration = await _iterate(client)

    assert iteration.status is VerificationStatus.AGENT_ERROR
    assert iteration.model is None
    assert iteration.result is not None
    assert iteration.result.error_detail


async def test_engine_result_is_not_overwritten_by_the_agent() -> None:
    """Движок сказал — агент не переписывает: контрпример остаётся движковым."""
    client = FakeLLM(to_wire_model(_cited_model()), explanation_payload())

    iteration = await _iterate(client)

    assert iteration.result is not None
    assert iteration.result.counterexample is not None
    assert len(iteration.result.counterexample.steps) == 4
