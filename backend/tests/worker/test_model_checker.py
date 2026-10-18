"""Проверки адаптера движка на настоящем TLC.

Тесты с внешними зависимостями: им нужен ``tla2tools.jar``. Модели берутся из
``tests.domain.case_examples``, чтобы фикстура кейса не расходилась между
доменными и движковыми тестами.
"""

import asyncio
import subprocess
from pathlib import Path
from typing import Any

import pytest

from app.domain.behavioral_model import BehavioralModel, Property
from app.worker.model_checker import EngineSettings, ModelChecker
from tests.domain.case_examples import case_model, fixed_model
from tests.worker.support import JAR, requires_java

pytestmark = [pytest.mark.integration, requires_java]


def _model(document: dict[str, Any]) -> BehavioralModel:
    return BehavioralModel.model_validate(document)


def _by_type(model: BehavioralModel, prop_type: str) -> Property:
    return next(prop for prop in model.properties if prop.type == prop_type)


def _checker(tmp_path: Path, **overrides: float | int | str) -> ModelChecker:
    """Движок для одного теста: таймаут и лимит задаются явно."""
    return ModelChecker(
        EngineSettings(
            jar=JAR,
            timeout_seconds=float(overrides.get("timeout_seconds", 30)),
            state_limit=int(overrides.get("state_limit", 1_000_000)),
            workers="1",
            work_dir=tmp_path,
        )
    )


def _wide_model(width: int) -> BehavioralModel:
    """Модель с экспоненциальным числом состояний: перебор не успевает за тик.

    Каждая переменная переключается один раз, поэтому состояний ровно ``2**width``,
    и обход не заканчивается за секунды — на этом построены проверки таймаута и
    лимита состояний.
    """
    return _model(
        {
            "variables": [
                {"name": f"v{index}", "type": "enum", "values": ["a", "b"]}
                for index in range(width)
            ],
            "initial": {f"v{index}": "a" for index in range(width)},
            "transitions": [
                {
                    "name": f"Flip{index}",
                    "guard": {"eq": [{"var": f"v{index}"}, "a"]},
                    "effects": [{"set": [f"v{index}", "b"]}],
                }
                for index in range(width)
            ],
            "properties": [
                {
                    "id": "P1",
                    "type": "invariant",
                    "expression": {"in": [{"var": "v0"}, ["a", "b"]]},
                }
            ],
        }
    )


def test_runs_case_model_and_reports_property_holds(tmp_path: Path) -> None:
    """Исправленная модель кейса проходит проверку."""
    model = _model(fixed_model())
    prop = _by_type(model, "forbidden_state")

    outcome = asyncio.run(_checker(tmp_path).check(model, prop))

    assert outcome.result.status == "PROPERTY_HOLDS"
    assert outcome.result.counterexample is None
    assert outcome.result.error_detail is None


def test_reports_property_violated_with_named_transitions(tmp_path: Path) -> None:
    """Нарушенное свойство даёт контрпример с именами переходов."""
    model = _model(case_model())
    prop = _by_type(model, "forbidden_state")

    outcome = asyncio.run(_checker(tmp_path).check(model, prop))

    steps = outcome.result.counterexample.steps if outcome.result.counterexample else None
    assert outcome.result.status == "PROPERTY_VIOLATED"
    assert steps is not None
    assert [step.transition for step in steps][-4:] == [None, "Approve", "Cancel", "Execute"]


def test_reads_violation_of_the_initial_state(tmp_path: Path) -> None:
    """Инвариант, неверный уже в начальном состоянии, — обычный результат, не сбой."""
    model = _model(case_model())
    prop = _by_type(model, "invariant")

    outcome = asyncio.run(_checker(tmp_path).check(model, prop))

    assert outcome.result.status == "PROPERTY_VIOLATED"
    assert outcome.result.counterexample is not None
    assert len(outcome.result.counterexample.steps) == 1


def test_deadlock_free_reports_violation_at_the_stuck_state(tmp_path: Path) -> None:
    """``deadlock_free`` находит застрявшее состояние."""
    model = _model(fixed_model())
    prop = _by_type(model, "deadlock_free")

    outcome = asyncio.run(_checker(tmp_path).check(model, prop))

    assert outcome.result.status == "PROPERTY_VIOLATED"
    assert outcome.result.error_detail is None


def test_reachable_state_is_reported_as_holds(tmp_path: Path) -> None:
    """``reachable`` проверяется отрицанием, и достижимое состояние — это успех."""
    model = _model(fixed_model())
    prop = _by_type(model, "reachable")

    outcome = asyncio.run(_checker(tmp_path).check(model, prop))

    assert outcome.result.status == "PROPERTY_HOLDS"
    assert outcome.result.counterexample is None


def test_unreachable_state_is_reported_as_violated(tmp_path: Path) -> None:
    """Недостижимое состояние — нарушение, и оно не выдаётся за успех."""
    document = fixed_model()
    document["transitions"] = [
        transition
        for transition in document["transitions"]
        if transition["name"] in {"Approve", "Cancel"}
    ]
    document["properties"] = [
        {
            "id": "R1",
            "type": "reachable",
            "expression": {"eq": [{"var": "status"}, "Executed"]},
        }
    ]
    model = _model(document)

    outcome = asyncio.run(_checker(tmp_path).check(model, _by_type(model, "reachable")))

    assert outcome.result.status == "PROPERTY_VIOLATED"
    assert outcome.result.counterexample is not None
    assert outcome.result.error_detail


def test_kills_run_on_timeout_and_reports_timeout(tmp_path: Path) -> None:
    """Зависший перебор снимается по таймауту и даёт TIMEOUT, а не успех."""
    model = _wide_model(26)

    outcome = asyncio.run(
        _checker(tmp_path, timeout_seconds=3).check(model, _by_type(model, "invariant"))
    )

    assert outcome.result.status == "TIMEOUT"
    assert "3" in (outcome.result.error_detail or "")


def test_reports_state_limit_when_exploration_outgrows_budget(tmp_path: Path) -> None:
    """Перебор дорос сверх лимита — это STATE_LIMIT_REACHED, а не PROPERTY_HOLDS."""
    model = _wide_model(26)

    outcome = asyncio.run(
        _checker(tmp_path, state_limit=500).check(model, _by_type(model, "invariant"))
    )

    assert outcome.result.status == "STATE_LIMIT_REACHED"
    assert "500" in (outcome.result.error_detail or "")


def test_leaves_no_tlc_process_behind_after_timeout(tmp_path: Path) -> None:
    """Процесс снимается вместе с группой: перебор не должен жить в фоне."""
    model = _wide_model(26)

    asyncio.run(_checker(tmp_path, timeout_seconds=3).check(model, _by_type(model, "invariant")))

    assert _java_processes() == []


def test_reports_engine_error_when_jar_is_missing(tmp_path: Path) -> None:
    """Недоступный jar — ENGINE_ERROR, а не молчание."""
    settings = EngineSettings(
        jar=Path("/nonexistent/tla2tools.jar"),
        timeout_seconds=5,
        state_limit=1_000,
        workers="1",
        work_dir=tmp_path,
    )
    model = _model(fixed_model())

    outcome = asyncio.run(ModelChecker(settings).check(model, _by_type(model, "forbidden_state")))

    assert outcome.result.status == "ENGINE_ERROR"
    assert "tla2tools.jar" in (outcome.result.error_detail or "")


def test_reports_engine_version_actually_used(tmp_path: Path) -> None:
    """Версия движка читается из его вывода, а не подставляется константой."""
    model = _model(fixed_model())

    outcome = asyncio.run(_checker(tmp_path).check(model, _by_type(model, "forbidden_state")))

    version = outcome.result.engine_version
    assert version is not None
    assert version and version in outcome.output


def test_reports_statistics_with_all_three_counters(tmp_path: Path) -> None:
    """Статистика приходит полной: домен требует все три счётчика сразу."""
    model = _model(fixed_model())

    outcome = asyncio.run(_checker(tmp_path).check(model, _by_type(model, "forbidden_state")))

    statistics = outcome.result.statistics
    assert statistics is not None
    assert statistics.states_generated >= 1
    assert statistics.distinct_states <= statistics.states_generated
    assert statistics.depth >= 1


def test_reports_model_invalid_for_a_broken_spec(tmp_path: Path) -> None:
    """Спецификация, которую SANY не может разобрать, — MODEL_INVALID, не ENGINE_ERROR."""
    model = _model(fixed_model())
    checker = _checker(tmp_path)
    broken = Path(tmp_path) / "broken"
    broken.mkdir()
    (broken / "Model.tla").write_text("MODULE Model\nInit ==\n====\n", encoding="utf-8")

    result = asyncio.run(
        checker._check_syntax(broken / "Model.tla", _by_type(model, "deadlock_free"))
    )

    assert result is not None
    assert result.status == "MODEL_INVALID"


def _java_processes() -> list[str]:
    """Запущенные процессы TLC: после прогона их быть не должно."""
    found = subprocess.run(
        ["pgrep", "-af", "tlc2.TLC"], capture_output=True, text=True, check=False
    )
    return [line for line in found.stdout.splitlines() if "pgrep" not in line]
