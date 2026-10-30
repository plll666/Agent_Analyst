"""Граф итерации: форма DAG и поведение перестроений.

Форма проверяется по рёбрам, которые отдаёт сам LangGraph, а не по нашему
описанию: тест должен ловить случай, когда граф собрался с циклом.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.agent.graph import CycleLimits, compiled_graph, graph_mermaid, run_iteration
from app.domain.behavioral_model import BehavioralModel, Property
from app.domain.decision import AnalysisDecision
from app.domain.verification import VerificationResult, VerificationStatus
from tests.agent.support import FailingLLM, FakeLLM, explanation_payload, to_wire_model
from tests.domain.case_examples import CASE_RESULT_VIOLATED

REQUIREMENT = (
    "Заявка после согласования может быть исполнена. "
    "Пользователь может отменить заявку до исполнения."
)
QUOTE = "Заявка после согласования может быть исполнена"
LIMITS = CycleLimits(build_attempts=1, max_rebuilds=2, explanation_attempts=1)
STEPS = {
    "build_0",
    "gate_0",
    "check_0",
    "explain_0",
    "build_1",
    "gate_1",
    "check_1",
    "explain_1",
    "build_2",
    "gate_2",
    "check_2",
    "explain_2",
    "finish",
    "fail",
}


def _cited_model() -> dict[str, Any]:
    """Модель, у которой правила подкреплены цитатой из текста."""
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
    """Та же модель, но правила ничем не подкреплены."""
    document = _cited_model()
    document["transitions"][0].pop("source_reference")
    document["properties"][0].pop("source_reference")
    return document


def _agent_error_payload(hypothesis: str) -> dict[str, Any]:
    """Объяснение, которое признаёт ошибку модели, а не требования."""
    return {
        **explanation_payload(),
        "root_cause": "AGENT_ERROR",
        "hypothesis": hypothesis,
    }


async def _violated(_model: BehavioralModel, _prop: Property) -> VerificationResult:
    """Движок нашёл нарушение."""
    return VerificationResult.model_validate(CASE_RESULT_VIOLATED)


def _edges(max_rebuilds: int = 2) -> set[tuple[str, str]]:
    """Все рёбра графа, включая условные."""
    return {(edge.source, edge.target) for edge in compiled_graph(max_rebuilds).get_graph().edges}


def _is_acyclic(nodes: set[str], edges: set[tuple[str, str]]) -> bool:
    """Топологическая сортировка: если прошли все узлы, цикла нет."""
    outgoing: dict[str, list[str]] = defaultdict(list)
    incoming = dict.fromkeys(nodes, 0)
    for source, target in edges:
        if source in incoming and target in incoming:
            outgoing[source].append(target)
            incoming[target] += 1
    queue = [node for node, degree in incoming.items() if degree == 0]
    visited = 0
    while queue:
        node = queue.pop()
        visited += 1
        for target in outgoing[node]:
            incoming[target] -= 1
            if incoming[target] == 0:
                queue.append(target)
    return visited == len(nodes)


def test_cycle_is_a_dag() -> None:
    """В графе нет рёбер назад: перестройка развёрнута в цепочку."""
    graph = compiled_graph(2).get_graph()
    nodes = set(graph.nodes)
    edges = _edges()

    assert nodes >= STEPS
    assert _is_acyclic(nodes, edges)
    # Перестройка идёт только вперёд: gate_0 → build_1 → ... → explain_2.
    assert ("gate_0", "build_1") in edges
    assert ("gate_1", "build_2") in edges
    assert ("explain_0", "build_1") in edges
    assert ("explain_1", "build_2") in edges
    assert ("check_0", "explain_0") in edges
    # Последняя ступень уже не может отправить модель на новую сборку.
    assert ("gate_2", "build_3") not in edges
    assert ("explain_2", "build_3") not in edges
    assert ("gate_2", "fail") in edges
    assert ("explain_2", "finish") in edges


def test_graph_shape_follows_the_rebuild_limit() -> None:
    """Лимит перестроений — это форма графа, а не число итераций в коде."""
    edges = _edges(max_rebuilds=0)
    nodes = {node for edge in edges for node in edge}

    assert "build_0" in nodes
    assert "build_1" not in nodes
    assert "check_0" in nodes
    assert "explain_0" in nodes
    assert ("gate_0", "fail") in edges
    assert ("gate_0", "check_0") in edges
    assert ("explain_0", "finish") in edges


def test_mermaid_keeps_the_same_steps() -> None:
    """Схема для документации показывает те же шаги, что и рабочий граф."""
    schema = graph_mermaid(2)

    assert "build_0" in schema
    assert "check_0" in schema
    assert "explain_0" in schema
    assert "gate_2" in schema
    assert "finish" in schema


async def test_rebuild_gets_feedback_and_full_attempts() -> None:
    """Перестроение идёт с замечаниями и полным бюджетом попыток модели."""
    client = FakeLLM(
        to_wire_model(_uncited_model()), to_wire_model(_cited_model()), explanation_payload()
    )

    iteration = await run_iteration(
        client=client,
        requirement_text=REQUIREMENT,
        check_property=_violated,
        limits=CycleLimits(build_attempts=3, max_rebuilds=2, explanation_attempts=1),
        reasoning=True,
    )

    assert iteration.status is VerificationStatus.PROPERTY_VIOLATED
    assert iteration.rebuilds == 1
    assert len(client.calls) == 3
    rebuild = client.calls[1]
    assert rebuild["attempts"] == 3
    assert rebuild["reasoning"] is True
    assert "source_reference" in rebuild["user"] or "цитат" in rebuild["user"].lower()


async def test_reasoning_reaches_the_explanation() -> None:
    """Режим рассуждений — свойство всего прогона, а не только сборки модели."""
    client = FakeLLM(to_wire_model(_cited_model()), explanation_payload())

    await run_iteration(
        client=client,
        requirement_text=REQUIREMENT,
        check_property=_violated,
        limits=LIMITS,
        reasoning=True,
    )

    assert client.calls[-1]["prompt_version"].startswith("explanation")
    assert client.calls[-1]["reasoning"] is True


async def test_agent_error_rebuilds_the_model_with_the_explanation_as_feedback() -> None:
    """Ошибку модели агент исправляет сам, не задавая вопрос пользователю."""
    hypothesis = "P1 запрещает отмену вместо исполнения отменённой заявки."
    client = FakeLLM(
        to_wire_model(_cited_model()),
        _agent_error_payload(hypothesis),
        to_wire_model(_cited_model()),
        explanation_payload(),
    )

    iteration = await run_iteration(
        client=client,
        requirement_text=REQUIREMENT,
        check_property=_violated,
        limits=LIMITS,
    )

    assert iteration.status is VerificationStatus.PROPERTY_VIOLATED
    assert iteration.rebuilds == 1
    assert iteration.decision is AnalysisDecision.ASK
    assert iteration.explanation.question
    assert len(client.calls) == 4

    rebuild = client.calls[2]
    assert rebuild["prompt_version"].startswith("modeling")
    assert hypothesis in rebuild["user"]
    assert "К прошлой модели есть замечания" in rebuild["user"]


async def test_agent_error_without_rebuild_budget_stops_without_a_question() -> None:
    """Если перестраивать уже некуда, вопрос пользователю не задаётся."""
    client = FakeLLM(
        to_wire_model(_cited_model()),
        _agent_error_payload("P1 запрещает отмену вместо исполнения."),
    )

    iteration = await run_iteration(
        client=client,
        requirement_text=REQUIREMENT,
        check_property=_violated,
        limits=CycleLimits(build_attempts=1, max_rebuilds=0, explanation_attempts=1),
    )

    assert iteration.status is VerificationStatus.PROPERTY_VIOLATED
    assert iteration.rebuilds == 0
    assert iteration.decision is AnalysisDecision.STOP
    assert iteration.explanation.question is None
    assert len(client.calls) == 2


async def test_repeated_agent_error_stops_instead_of_rebuilding_forever() -> None:
    """То же замечание второй раз — повод остановиться, а не строить снова."""
    payload = _agent_error_payload("P1 запрещает отмену вместо исполнения.")
    client = FakeLLM(
        to_wire_model(_cited_model()),
        payload,
        to_wire_model(_cited_model()),
        payload,
    )

    iteration = await run_iteration(
        client=client,
        requirement_text=REQUIREMENT,
        check_property=_violated,
        limits=LIMITS,
    )

    assert iteration.status is VerificationStatus.PROPERTY_VIOLATED
    assert iteration.rebuilds == 1
    assert iteration.decision is AnalysisDecision.STOP
    assert iteration.explanation.question is None
    assert len(client.calls) == 4


async def test_schema_errors_are_kept_in_the_error_detail() -> None:
    """Невалидный структурный ответ не теряет причину в «модель не ответила»."""
    client = FakeLLM({}, {}, {})

    iteration = await run_iteration(
        client=client,
        requirement_text=REQUIREMENT,
        check_property=_violated,
        limits=CycleLimits(build_attempts=3, max_rebuilds=0, explanation_attempts=1),
    )

    assert iteration.status is VerificationStatus.AGENT_ERROR
    assert iteration.model is None
    assert iteration.result is not None
    detail = iteration.result.error_detail or ""
    assert "validation error" in detail.lower()


async def test_same_gate_problems_stop_the_chain() -> None:
    """Повтор тех же замечаний — повод остановиться, а не строить третий раз."""
    client = FakeLLM(to_wire_model(_uncited_model()), to_wire_model(_uncited_model()))

    iteration = await run_iteration(
        client=client,
        requirement_text=REQUIREMENT,
        check_property=_violated,
        limits=LIMITS,
    )

    assert iteration.status is VerificationStatus.AGENT_ERROR
    assert iteration.decision is AnalysisDecision.STOP
    assert iteration.rebuilds == 1
    assert len(client.calls) == 2


async def test_unavailable_provider_stops_before_the_gate() -> None:
    """Провайдер не ответил — ворота не запускаются, модель не выдумывается."""
    client = FailingLLM(failures=5)

    iteration = await run_iteration(
        client=client,
        requirement_text=REQUIREMENT,
        check_property=_violated,
        limits=LIMITS,
    )

    assert iteration.status is VerificationStatus.AGENT_ERROR
    assert iteration.model is None
    # FailingLLM падает до записи вызова: важно, что до ворот дело не дошло.
    assert iteration.gate_problems
    assert iteration.result is not None
    assert iteration.result.error_detail
