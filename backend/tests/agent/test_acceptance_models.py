"""Приёмка спринта 3: модели из ТЗ, четыре типа свойств и повторяемость вердикта.

Тесты идут через настоящий TLC, поэтому помечены ``integration`` и ``requires_java``:
без ``tla2tools.jar`` они пропускаются, а не подменяются заглушкой. Модель
агенту поставляет FakeLLM — проверяется цикл целиком (ворота, движок, итог), но
без сетевого вызова настоящей LLM.

Критерии — из кейса: модель 1 даёт ``PROPERTY_VIOLATED`` с путём
``Created → Approve → Cancel → Execute``, модель 2 — ``PROPERTY_HOLDS``.
Повторный прогон при тех же настройках обязан дать тот же вердикт.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.agent.generation import GenerationProfile, generation_profile
from app.agent.graph import CheckProperty, CycleLimits, run_iteration
from app.domain.behavioral_model import BehavioralModel, Property
from app.domain.verification import VerificationResult, VerificationStatus
from app.worker.model_checker import EngineSettings, ModelChecker
from tests.agent.support import FakeLLM, cited_payload, explanation_payload, settings
from tests.domain.case_examples import case_model, fixed_model
from tests.worker.support import JAR, acceptance_model, requires_java

pytestmark = [pytest.mark.integration, requires_java]

REQUIREMENT = (
    "Заявка после согласования может быть исполнена. "
    "Пользователь может отменить заявку до исполнения."
)
QUOTE = "Заявка после согласования может быть исполнена"
LIMITS = CycleLimits(build_attempts=1, max_rebuilds=0, explanation_attempts=1)


def _checker(tmp_path: Path) -> ModelChecker:
    return ModelChecker(
        EngineSettings(
            jar=JAR,
            timeout_seconds=60,
            state_limit=100_000,
            workers="1",
            work_dir=tmp_path,
        )
    )


def _checker_adapter(checker: ModelChecker) -> CheckProperty:
    async def check_property(model: BehavioralModel, prop: Property) -> VerificationResult:
        outcome = await checker.check(model, prop)
        return outcome.result

    return check_property


def _model(document: dict[str, Any]) -> BehavioralModel:
    return BehavioralModel.model_validate(document)


def _by_type(model: BehavioralModel, prop_type: str) -> Property:
    return next(prop for prop in model.properties if prop.type == prop_type)


def _profile() -> GenerationProfile:
    return generation_profile(
        settings(),
        build_attempts=LIMITS.build_attempts,
        max_rebuilds=LIMITS.max_rebuilds,
        explanation_attempts=LIMITS.explanation_attempts,
        reasoning=None,
    )


async def _run_acceptance(checker: ModelChecker, document: dict[str, Any], *, explain: bool) -> Any:
    client = FakeLLM(cited_payload(document, QUOTE), *([explanation_payload()] if explain else []))
    return await run_iteration(
        client=client,
        requirement_text=REQUIREMENT,
        check_property=_checker_adapter(checker),
        limits=LIMITS,
        generation=_profile(),
    )


async def test_acceptance_model_1_is_violated_with_the_case_path(tmp_path: Path) -> None:
    """Acceptance test 1: цикл находит нарушение и сохраняет путь из кейса."""
    iteration = await _run_acceptance(_checker(tmp_path), acceptance_model(False), explain=True)

    assert iteration.status is VerificationStatus.PROPERTY_VIOLATED
    assert iteration.explanation.hypothesis is not None
    assert iteration.explanation.root_cause is not None
    counterexample = iteration.result.counterexample
    assert counterexample is not None
    transitions = [step.transition for step in counterexample.steps][-4:]
    assert transitions == [None, "Approve", "Cancel", "Execute"]
    assert counterexample.steps[0].state["status"] == "Created"
    assert counterexample.steps[-1].state["status"] == "Executed"


async def test_acceptance_model_2_holds_and_asks_nothing(tmp_path: Path) -> None:
    """Acceptance test 2: исправленная модель проходит, объяснение не требуется."""
    iteration = await _run_acceptance(_checker(tmp_path), acceptance_model(True), explain=False)

    assert iteration.status is VerificationStatus.PROPERTY_HOLDS
    assert iteration.result.counterexample is None
    assert iteration.explanation.question is None


async def test_verdict_is_repeatable_for_the_same_model(tmp_path: Path) -> None:
    """А8: одинаковые модель и настройки дают одинаковый вердикт и профиль."""
    checker = _checker(tmp_path)
    first = await _run_acceptance(checker, acceptance_model(False), explain=True)
    second = await _run_acceptance(checker, acceptance_model(False), explain=True)

    assert first.status is second.status is VerificationStatus.PROPERTY_VIOLATED
    assert first.result.property_id == second.result.property_id
    assert first.generation is not None and second.generation is not None
    assert first.generation.fingerprint() == second.generation.fingerprint()

    def _path(iteration: Any) -> list[str | None]:
        counterexample = iteration.result.counterexample
        assert counterexample is not None
        return [step.transition for step in counterexample.steps]

    assert _path(first) == _path(second)


async def test_four_property_types_have_expected_outcomes(tmp_path: Path) -> None:
    """Все четыре типа свойств проверяются настоящим TLC с известным исходом."""
    checker = _checker(tmp_path)
    broken = _model(case_model())
    corrected = _model(fixed_model())

    invariant = await checker.check(broken, _by_type(broken, "invariant"))
    assert invariant.result.status is VerificationStatus.PROPERTY_VIOLATED
    assert invariant.result.counterexample is not None
    assert len(invariant.result.counterexample.steps) == 1

    forbidden = await checker.check(broken, _by_type(broken, "forbidden_state"))
    assert forbidden.result.status is VerificationStatus.PROPERTY_VIOLATED

    reachable = await checker.check(corrected, _by_type(corrected, "reachable"))
    assert reachable.result.status is VerificationStatus.PROPERTY_HOLDS
    assert reachable.result.counterexample is None

    deadlock = await checker.check(corrected, _by_type(corrected, "deadlock_free"))
    assert deadlock.result.status is VerificationStatus.PROPERTY_VIOLATED
