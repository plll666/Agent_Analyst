"""События этапов: форма Stage, репортер и наблюдаемость DAG-итерации.

Контракт спринта 3 (§5.1) задаёт поля Stage и правило «один этап — один
``stage_id``». Здесь проверяется и сама форма события, и то, что граф реально
сообщает о сборке, воротах, проверке, объяснении и перестроениях.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from app.agent.graph import CycleLimits, run_iteration
from app.agent.stages import (
    REASON_GATE_REJECTED,
    REASON_INVALID_RESPONSE,
    REASON_MODEL_INTERPRETATION_ERROR,
    AgentEvent,
    AgentRebuild,
    Stage,
    StageEmitter,
    StageReporter,
)
from app.domain.behavioral_model import BehavioralModel, Property
from app.domain.verification import VerificationResult
from tests.agent.support import FakeLLM, cited_payload, explanation_payload
from tests.domain.case_examples import CASE_RESULT_VIOLATED, case_model

REQUIREMENT = (
    "Заявка после согласования может быть исполнена. "
    "Пользователь может отменить заявку до исполнения."
)
QUOTE = "Заявка после согласования может быть исполнена"
LIMITS = CycleLimits(build_attempts=1, max_rebuilds=2, explanation_attempts=1)


class Collector:
    """Эмиттер, складывающий события в список для проверок."""

    def __init__(self) -> None:
        self.events: list[AgentEvent] = []

    async def __call__(self, event: AgentEvent) -> None:
        self.events.append(event)


def _stage(**overrides: Any) -> Stage:
    values: dict[str, Any] = {
        "stage_id": "s1",
        "scope": "agent",
        "name": "build",
        "state": "RUNNING",
        "build_index": 0,
        "attempt": 1,
        "started_at": datetime.now(UTC),
    }
    values.update(overrides)
    return Stage(**values)


def _bad_emitter_factory() -> StageEmitter:
    class Failing:
        async def __call__(self, event: AgentEvent) -> None:
            raise RuntimeError(f"backend недоступен: {event}")

    return Failing()


def _cited_model() -> dict[str, Any]:
    return cited_payload(case_model(), QUOTE)


def _uncited_model() -> dict[str, Any]:
    document = _cited_model()
    for transition in document["transitions"]:
        transition["source_reference"] = None
    for prop in document["properties"]:
        prop["source_reference"] = None
    return document


def _explanation_batch() -> tuple[dict[str, Any], ...]:
    """Объяснение, согласованное с трассой из четырёх шагов."""
    return (explanation_payload(),)


async def _violated(
    model: BehavioralModel, prop: Property, *, emit_stage: StageEmitter | None = None
) -> VerificationResult:
    _ = (model, prop, emit_stage)
    return VerificationResult.model_validate(CASE_RESULT_VIOLATED)


def _stages(events: list[AgentEvent]) -> list[Stage]:
    return [event for event in events if isinstance(event, Stage)]


def _rebuilds(events: list[AgentEvent]) -> list[AgentRebuild]:
    return [event for event in events if isinstance(event, AgentRebuild)]


def test_stage_completion_fields_are_consistent() -> None:
    """Незавершённый этап не имеет времени конца, завершённый — обязан."""
    with pytest.raises(ValidationError, match="finished_at"):
        _stage(finished_at=datetime.now(UTC))

    with pytest.raises(ValidationError, match="finished_at"):
        _stage(state="SUCCEEDED")

    skipped = _stage(state="SKIPPED")
    assert skipped.finished_at is None


async def test_reporter_sends_start_and_finish_with_the_same_id() -> None:
    collector = Collector()
    reporter = StageReporter(collector)

    stage_id = await reporter.start("build", build_index=1, message="строим")
    await reporter.finish(stage_id, state="SUCCEEDED", message="готово")

    assert [stage.state for stage in _stages(collector.events)] == ["RUNNING", "SUCCEEDED"]
    started, finished = _stages(collector.events)
    assert started.stage_id == finished.stage_id == stage_id
    assert finished.duration_ms is not None and finished.duration_ms >= 0
    assert finished.finished_at is not None


async def test_child_emitter_fills_the_parent_stage() -> None:
    """Этап ядра вкладывается в agent/check, даже если родителя не назвал."""
    collector = Collector()
    reporter = StageReporter(collector)
    check_id = await reporter.start("check", build_index=0, property_id="P1")

    child = reporter.child(check_id)
    await child(
        _stage(stage_id="core-1", scope="core", name="tlc_run", attempt=1, property_id="P1")
    )

    core = _stages(collector.events)[-1]
    assert core.parent_stage_id == check_id


async def test_reporter_without_emitter_is_a_no_op() -> None:
    reporter = StageReporter()

    stage_id = await reporter.start("build")
    await reporter.finish(stage_id, state="SUCCEEDED")
    await reporter.rebuild(from_build_index=0, to_build_index=1, reason_code=REASON_GATE_REJECTED)

    assert stage_id == ""


async def test_failing_emitter_does_not_break_the_iteration() -> None:
    reporter = StageReporter(_bad_emitter_factory())

    stage_id = await reporter.start("build")
    await reporter.finish(stage_id, state="SUCCEEDED")
    await reporter.rebuild(from_build_index=0, to_build_index=1, reason_code=REASON_GATE_REJECTED)


async def test_iteration_reports_all_agent_stages() -> None:
    collector = Collector()
    client = FakeLLM(_cited_model(), *_explanation_batch())

    iteration = await run_iteration(
        client=client,
        requirement_text=REQUIREMENT,
        check_property=_violated,
        limits=LIMITS,
        emit_stage=collector,
    )

    assert iteration.status.value == "PROPERTY_VIOLATED"
    stages = _stages(collector.events)
    names = [stage.name for stage in stages]
    assert names[:4] == ["build", "build", "gate", "gate"]
    assert "check" in names and "explain" in names
    assert all(stage.scope == "agent" for stage in stages)
    assert all(stage.build_index == 0 for stage in stages)
    for running, finished in zip(stages[::2], stages[1::2], strict=True):
        assert running.stage_id == finished.stage_id
        assert running.state == "RUNNING"
        assert finished.state in {"SUCCEEDED", "FAILED"}


async def test_gate_rejection_reports_a_rebuild() -> None:
    """Перестройка после ворот видна как отдельное событие с причиной."""
    collector = Collector()
    client = FakeLLM(_uncited_model(), _cited_model(), *_explanation_batch())

    iteration = await run_iteration(
        client=client,
        requirement_text=REQUIREMENT,
        check_property=_violated,
        limits=LIMITS,
        emit_stage=collector,
    )

    assert iteration.rebuilds == 1
    rebuilds = _rebuilds(collector.events)
    assert len(rebuilds) == 1
    assert rebuilds[0].reason_code == REASON_GATE_REJECTED
    assert (rebuilds[0].from_build_index, rebuilds[0].to_build_index) == (0, 1)
    gate_failures = [stage for stage in _stages(collector.events) if stage.state == "FAILED"]
    assert gate_failures and gate_failures[0].reason_code == REASON_GATE_REJECTED
    assert {stage.build_index for stage in _stages(collector.events)} == {0, 1}


async def test_interpretation_error_reports_a_rebuild() -> None:
    """Ошибку модели агент исправляет сам, и это видно в событиях."""
    agent_error = {**explanation_payload(), "root_cause": "AGENT_ERROR"}
    collector = Collector()
    client = FakeLLM(
        _cited_model(),
        agent_error,
        _cited_model(),
        *_explanation_batch(),
    )

    iteration = await run_iteration(
        client=client,
        requirement_text=REQUIREMENT,
        check_property=_violated,
        limits=LIMITS,
        emit_stage=collector,
    )

    assert iteration.rebuilds == 1
    rebuilds = _rebuilds(collector.events)
    assert [rebuild.reason_code for rebuild in rebuilds] == [REASON_MODEL_INTERPRETATION_ERROR]
    assert (rebuilds[0].from_build_index, rebuilds[0].to_build_index) == (0, 1)


async def test_build_failure_is_a_failed_stage() -> None:
    collector = Collector()
    client = FakeLLM({}, {}, {})

    iteration = await run_iteration(
        client=client,
        requirement_text=REQUIREMENT,
        check_property=_violated,
        limits=CycleLimits(build_attempts=3, max_rebuilds=0, explanation_attempts=1),
        emit_stage=collector,
    )

    assert iteration.status.value == "AGENT_ERROR"
    stages = _stages(collector.events)
    assert len(stages) == 2
    assert stages[1].state == "FAILED"
    assert stages[1].reason_code == REASON_INVALID_RESPONSE
    assert not _rebuilds(collector.events)


async def test_core_stages_are_nested_under_check() -> None:
    """Адаптер ядра получает эмиттер, а его этапы ссылаются на agent/check."""
    collector = Collector()

    async def check_property(
        model: BehavioralModel, prop: Property, *, emit_stage: StageEmitter | None = None
    ) -> VerificationResult:
        _ = model
        assert emit_stage is not None
        await emit_stage(
            _stage(
                stage_id="core-1",
                scope="core",
                name="tlc_run",
                property_id=prop.id,
            )
        )
        return VerificationResult.model_validate(CASE_RESULT_VIOLATED)

    client = FakeLLM(_cited_model(), *_explanation_batch())
    await run_iteration(
        client=client,
        requirement_text=REQUIREMENT,
        check_property=check_property,
        limits=CycleLimits(build_attempts=1, max_rebuilds=0, explanation_attempts=1),
        emit_stage=collector,
    )

    core = next(stage for stage in _stages(collector.events) if stage.stage_id == "core-1")
    check = next(stage for stage in _stages(collector.events) if stage.name == "check")
    assert core.parent_stage_id == check.stage_id
    assert core.property_id == check.property_id


def test_stage_serializes_to_contract_shape() -> None:
    """Снимок этапа несёт все поля контракта и не теряет время."""
    payload = _stage(
        parent_stage_id="parent",
        property_id="P1",
        state="SUCCEEDED",
        finished_at=datetime.now(UTC),
        duration_ms=12,
        reason_code=None,
        message="TLC проверяет свойство P1",
    ).model_dump(mode="json")

    assert payload["stage_id"] == "s1"
    assert payload["parent_stage_id"] == "parent"
    assert payload["scope"] == "agent"
    assert payload["build_index"] == 0
    assert payload["attempt"] == 1
    assert payload["duration_ms"] == 12
