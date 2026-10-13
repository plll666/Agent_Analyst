from copy import deepcopy
from typing import Any

import pytest

from app.domain.behavioral_model import BehavioralModel
from app.domain.verification import (
    Verification,
    VerificationExplanation,
    VerificationResult,
)
from tests.domain.case_examples import (
    CASE_MODEL,
    CASE_RESULT_VIOLATED,
    COMPLETE_RESULT,
    case_model,
    contract_model,
    contract_model_fixed,
    contract_result,
    fixed_model,
)
from tests.domain.helpers import assert_rejected

ALLOWED_STATUSES_WITHOUT_COUNTEREXAMPLE = [
    "PENDING",
    "PROPERTY_HOLDS",
    "MODEL_INVALID",
    "TIMEOUT",
    "STATE_LIMIT_REACHED",
    "ENGINE_ERROR",
]

STATUSES_REQUIRING_PROPERTY_ID = [
    "PROPERTY_HOLDS",
    "TIMEOUT",
    "STATE_LIMIT_REACHED",
    "ENGINE_ERROR",
]


def replace_transition(document: dict[str, Any], name: str, **changes: object) -> dict[str, Any]:
    for transition in document["transitions"]:
        if transition["name"] == name:
            transition.update(changes)
    return document


def replace_guard(document: dict[str, Any], name: str, guard: object) -> dict[str, Any]:
    return replace_transition(document, name, guard=guard)


def test_rejects_duplicate_variable_names() -> None:
    document = case_model()
    document["variables"].append({"name": "status", "type": "boolean"})

    assert_rejected(BehavioralModel, document, "variables: имя 'status' повторяется")


def test_rejects_unknown_variable_type() -> None:
    document = case_model()
    document["variables"][0]["type"] = "string"

    assert_rejected(BehavioralModel, document, "Input should be 'enum', 'boolean' or 'integer'")


def test_rejects_enum_without_values() -> None:
    assert_rejected(
        BehavioralModel,
        {
            "variables": [{"name": "status", "type": "enum"}],
            "initial": {"status": "Created"},
            "transitions": [],
            "properties": [],
        },
        "типа enum требует непустой список values",
    )


def test_rejects_enum_with_empty_values() -> None:
    assert_rejected(
        BehavioralModel,
        {
            "variables": [{"name": "status", "type": "enum", "values": []}],
            "initial": {"status": "Created"},
            "transitions": [],
            "properties": [],
        },
        "типа enum требует непустой список values",
    )


def test_rejects_enum_with_duplicate_values() -> None:
    document = case_model()
    document["variables"][0]["values"] = ["Created", "Approved", "Created"]

    assert_rejected(BehavioralModel, document, "значения домена повторяются")


def test_rejects_enum_with_bounds() -> None:
    document = case_model()
    document["variables"][0]["min"] = 0

    assert_rejected(BehavioralModel, document, "поля min и max к нему неприменимы")


def test_rejects_boolean_with_values() -> None:
    document = case_model()
    document["variables"][1]["values"] = ["true", "false"]

    assert_rejected(BehavioralModel, document, "типа boolean не принимает поля домена")


def test_rejects_boolean_with_bounds() -> None:
    document = case_model()
    document["variables"][1]["min"] = 0
    document["variables"][1]["max"] = 1

    assert_rejected(BehavioralModel, document, "типа boolean не принимает поля домена")


def test_rejects_integer_without_bounds() -> None:
    document = case_model()
    document["variables"][3] = {"name": "attempts", "type": "integer"}

    assert_rejected(BehavioralModel, document, "требует обе границы min и max")


def test_rejects_integer_with_only_one_bound() -> None:
    document = case_model()
    document["variables"][3] = {"name": "attempts", "type": "integer", "min": 0}

    assert_rejected(BehavioralModel, document, "требует обе границы min и max")


def test_rejects_integer_with_min_greater_than_max() -> None:
    document = case_model()
    document["variables"][3]["min"] = 5

    assert_rejected(BehavioralModel, document, "больше max=3")


def test_rejects_integer_with_enum_values() -> None:
    document = case_model()
    document["variables"][3]["values"] = ["0", "1", "2"]

    assert_rejected(BehavioralModel, document, "задаёт значения перечисления")


def test_rejects_variable_name_starting_with_digit() -> None:
    document = case_model()
    document["variables"][0]["name"] = "2status"

    assert_rejected(BehavioralModel, document, "should match pattern")


def test_rejects_variable_name_with_space() -> None:
    document = case_model()
    document["variables"][0]["name"] = "current status"

    assert_rejected(BehavioralModel, document, "should match pattern")


def test_rejects_unknown_variable_field() -> None:
    document = case_model()
    document["variables"][0]["title"] = "статус заявки"

    assert_rejected(BehavioralModel, document, "Extra inputs are not permitted")


def test_rejects_missing_initial() -> None:
    document = case_model()
    del document["initial"]

    assert_rejected(BehavioralModel, document, "Field required")


def test_rejects_empty_initial() -> None:
    document = case_model()
    document["initial"] = {}

    assert_rejected(BehavioralModel, document, "at least 1 item")


def test_rejects_initial_without_value_for_variable() -> None:
    document = case_model()
    del document["initial"]["attempts"]

    assert_rejected(BehavioralModel, document, "не задано начальное значение переменной 'attempts'")


def test_rejects_initial_key_matching_no_variable() -> None:
    document = case_model()
    document["initial"]["attempt"] = 0

    assert_rejected(BehavioralModel, document, "не соответствует ни одной переменной")


def test_rejects_initial_value_outside_enum_domain() -> None:
    document = case_model()
    document["initial"]["status"] = "Rejected"

    assert_rejected(BehavioralModel, document, "не входит в домен 'status'")


def test_rejects_initial_integer_above_range() -> None:
    document = case_model()
    document["initial"]["attempts"] = 5

    assert_rejected(BehavioralModel, document, "вне диапазона 'attempts' = [0, 3]")


def test_rejects_initial_integer_below_range() -> None:
    document = case_model()
    document["initial"]["attempts"] = -1

    assert_rejected(BehavioralModel, document, "вне диапазона 'attempts' = [0, 3]")


def test_rejects_initial_boolean_given_integer() -> None:
    document = case_model()
    document["initial"]["approved"] = 1

    assert_rejected(BehavioralModel, document, "типа boolean ждёт true/false")


def test_rejects_initial_integer_given_boolean() -> None:
    document = case_model()
    document["initial"]["attempts"] = True

    assert_rejected(BehavioralModel, document, "типа integer ждёт целое")


def test_rejects_initial_enum_given_number() -> None:
    document = case_model()
    document["initial"]["status"] = 1

    assert_rejected(BehavioralModel, document, "типа enum ждёт строку")


def test_rejects_duplicate_transition_names() -> None:
    document = case_model()
    document["transitions"].append(dict(document["transitions"][0]))

    assert_rejected(BehavioralModel, document, "transitions: имя 'Approve' повторяется 2 раза")


def test_rejects_transition_without_guard() -> None:
    document = case_model()
    del document["transitions"][0]["guard"]

    assert_rejected(BehavioralModel, document, "Field required")


def test_rejects_transition_without_effects() -> None:
    document = case_model()
    del document["transitions"][0]["effects"]

    assert_rejected(BehavioralModel, document, "Field required")


def test_rejects_transition_with_empty_effects() -> None:
    document = case_model()
    document["transitions"][0]["effects"] = []

    assert_rejected(BehavioralModel, document, "at least 1 item")


def test_rejects_duplicate_effect_target_in_one_transition() -> None:
    document = case_model()
    document["transitions"][0]["effects"] = [
        {"set": ["status", "Approved"]},
        {"set": ["approved", True]},
        {"set": ["approved", False]},
    ]

    assert_rejected(BehavioralModel, document, "уже присваивается в этом переходе")


def test_rejects_effect_operator_other_than_set() -> None:
    document = case_model()
    document["transitions"][0]["effects"] = [{"increment": ["attempts", 1]}]

    assert_rejected(BehavioralModel, document, "Extra inputs are not permitted")


def test_rejects_effect_targeting_unknown_variable() -> None:
    document = case_model()
    document["transitions"][0]["effects"] = [{"set": ["stage", "Approved"]}]

    assert_rejected(BehavioralModel, document, "присваивание неизвестной переменной 'stage'")


def test_rejects_effect_value_outside_enum_domain() -> None:
    document = case_model()
    document["transitions"][0]["effects"] = [{"set": ["status", "Rejected"]}]

    assert_rejected(BehavioralModel, document, "не входит в домен 'status'")


def test_rejects_effect_integer_given_boolean() -> None:
    document = case_model()
    document["transitions"][0]["effects"] = [{"set": ["attempts", True]}]

    assert_rejected(BehavioralModel, document, "типа integer ждёт целое")


def test_rejects_effect_value_outside_integer_range() -> None:
    document = case_model()
    document["transitions"][0]["effects"] = [{"set": ["attempts", 9]}]

    assert_rejected(BehavioralModel, document, "вне диапазона 'attempts' = [0, 3]")


def test_rejects_guard_referencing_unknown_variable() -> None:
    document = replace_guard(case_model(), "Approve", {"eq": [{"var": "stage"}, "Created"]})

    assert_rejected(BehavioralModel, document, "ссылка на неизвестную переменную 'stage'")


def test_rejects_nested_guard_referencing_unknown_variable() -> None:
    document = replace_guard(
        case_model(),
        "Approve",
        {
            "and": [
                {"eq": [{"var": "status"}, "Created"]},
                {"eq": [{"var": "missing"}, True]},
            ]
        },
    )

    assert_rejected(BehavioralModel, document, "ссылка на неизвестную переменную 'missing'")


def test_rejects_guard_literal_of_wrong_type() -> None:
    document = replace_guard(case_model(), "Approve", {"eq": [{"var": "approved"}, "yes"]})

    assert_rejected(BehavioralModel, document, "операнды разных типов: bool и str")


def test_rejects_guard_literal_outside_enum_domain() -> None:
    document = replace_guard(case_model(), "Approve", {"eq": [{"var": "status"}, "Rejected"]})

    assert_rejected(BehavioralModel, document, "не входит в домен 'status'")


def test_rejects_comparison_with_too_few_operands() -> None:
    document = replace_guard(case_model(), "Approve", {"eq": [{"var": "status"}]})

    assert_rejected(BehavioralModel, document, "should have at least 2 items")


def test_rejects_comparison_with_too_many_operands() -> None:
    document = replace_guard(
        case_model(),
        "Approve",
        {"eq": [{"var": "status"}, "Created", "Approved"]},
    )

    assert_rejected(BehavioralModel, document, "should have at most 2 items")


def test_rejects_conjunction_with_single_operand() -> None:
    document = replace_guard(case_model(), "Approve", {"and": [{"var": "approved"}]})

    assert_rejected(BehavioralModel, document, "should have at least 2 items")


def test_rejects_unknown_operator() -> None:
    document = replace_guard(case_model(), "Approve", {"greater": [{"var": "attempts"}, 1]})

    assert_rejected(BehavioralModel, document, "неизвестный оператор 'greater'")


def test_rejects_expression_with_several_keys() -> None:
    document = replace_guard(
        case_model(),
        "Approve",
        {"eq": [{"var": "status"}, "Created"], "and": [{"var": "approved"}]},
    )

    assert_rejected(BehavioralModel, document, "выражение задаётся одним ключом-оператором")


def test_rejects_membership_with_non_list() -> None:
    document = replace_guard(case_model(), "Cancel", {"in": [{"var": "status"}]})

    assert_rejected(BehavioralModel, document, 'оператор "in" ожидает два операнда')


def test_rejects_membership_with_empty_list() -> None:
    document = replace_guard(case_model(), "Cancel", {"in": [{"var": "status"}, []]})

    assert_rejected(BehavioralModel, document, "at least 1 item")


def test_rejects_membership_member_outside_enum_domain() -> None:
    document = replace_guard(
        case_model(),
        "Cancel",
        {"in": [{"var": "status"}, ["Created", "Rejected"]]},
    )

    assert_rejected(BehavioralModel, document, "не входит в домен 'status'")


def test_rejects_membership_member_of_wrong_type() -> None:
    document = replace_guard(case_model(), "Cancel", {"in": [{"var": "status"}, [1, 2]]})

    assert_rejected(BehavioralModel, document, "типа int, а сравнивается str")


def test_rejects_empty_variables() -> None:
    document = case_model()
    document["variables"] = []

    assert_rejected(BehavioralModel, document, "at least 1 item")


def test_rejects_empty_transitions() -> None:
    document = case_model()
    document["transitions"] = []

    assert_rejected(BehavioralModel, document, "at least 1 item")


def test_rejects_empty_properties() -> None:
    document = case_model()
    document["properties"] = []

    assert_rejected(BehavioralModel, document, "at least 1 item")


def test_rejects_unknown_top_level_field() -> None:
    document = case_model()
    document["description"] = "Жизненный цикл заявки"

    assert_rejected(BehavioralModel, document, "Extra inputs are not permitted")


def test_rejects_duplicate_property_ids() -> None:
    document = case_model()
    document["properties"].append(dict(document["properties"][2]))

    assert_rejected(BehavioralModel, document, "properties: имя 'P3' повторяется 2 раза")


def test_rejects_unknown_property_type() -> None:
    document = case_model()
    document["properties"][2]["type"] = "eventually"

    assert_rejected(
        BehavioralModel,
        document,
        "Input should be 'invariant', 'forbidden_state', 'reachable' or 'deadlock_free'",
    )


def test_rejects_invariant_without_expression() -> None:
    document = case_model()
    del document["properties"][0]["expression"]

    assert_rejected(BehavioralModel, document, "требует expression")


def test_rejects_reachable_without_expression() -> None:
    document = case_model()
    del document["properties"][2]["expression"]

    assert_rejected(BehavioralModel, document, "требует expression")


def test_rejects_deadlock_free_with_expression() -> None:
    document = case_model()
    document["properties"][3]["expression"] = {"eq": [{"var": "status"}, "Created"]}

    assert_rejected(BehavioralModel, document, "к нему неприменимо")


def test_rejects_property_referencing_unknown_variable() -> None:
    document = case_model()
    document["properties"][2]["expression"] = {"eq": [{"var": "stage"}, "Executed"]}

    assert_rejected(BehavioralModel, document, "ссылка на неизвестную переменную 'stage'")


def test_rejects_property_literal_of_wrong_type() -> None:
    document = case_model()
    document["properties"][2]["expression"] = {"eq": [{"var": "status"}, 5]}

    assert_rejected(BehavioralModel, document, "операнды разных типов: str и int")


def test_rejects_property_id_that_is_not_an_identifier() -> None:
    document = case_model()
    document["properties"][0]["id"] = "первое свойство"

    assert_rejected(BehavioralModel, document, "should match pattern")


def test_rejects_transition_name_that_is_not_an_identifier() -> None:
    document = case_model()
    document["transitions"][0]["name"] = "Approve Request"

    assert_rejected(BehavioralModel, document, "should match pattern")


def test_fixed_model_keeps_guards_and_effects_consistent() -> None:
    model = BehavioralModel.model_validate(fixed_model())

    cancel = next(item for item in model.transitions if item.name == "Cancel")
    targets = [effect.set[0] for effect in cancel.effects]

    assert targets == ["status", "cancelled", "approved"]


def test_rejects_contract_model_with_undeclared_variable() -> None:
    assert_rejected(
        BehavioralModel,
        contract_model(),
        "ссылка на неизвестную переменную 'cancelled'",
    )


def test_rejects_unknown_status() -> None:
    document = {"status": "PROPERTY_MAYBE_HOLD", "property_id": "P1", "engine": "TLC"}

    assert_rejected(VerificationResult, document, "Input should be")


def test_rejects_empty_property_id() -> None:
    assert_rejected(
        VerificationResult,
        {"status": "PROPERTY_HOLDS", "property_id": "", "engine": "TLC"},
        "at least 1 character",
    )


@pytest.mark.parametrize("status", STATUSES_REQUIRING_PROPERTY_ID)
def test_rejects_missing_property_id_on_status_that_names_it(status: str) -> None:
    document = {"status": status, "property_id": None, "engine": "TLC"}

    assert_rejected(VerificationResult, document, "property_id обязателен")


def test_rejects_related_requirement_with_unknown_field() -> None:
    document = {
        **contract_result(),
        "related_requirements": [
            {"paragraph_ref": "p3", "quote": "Заявка", "page": 4},
        ],
    }

    assert_rejected(VerificationResult, document, "Extra inputs are not permitted")


@pytest.mark.parametrize(
    "status",
    [
        "PROPERTY_HOLDS",
        "PROPERTY_VIOLATED",
        "TIMEOUT",
        "STATE_LIMIT_REACHED",
        "MODEL_INVALID",
        "ENGINE_ERROR",
    ],
)
def test_rejects_empty_business_summary_on_terminal_status(status: str) -> None:
    result = _result_for_status(status)

    with pytest.raises(Exception, match="business_summary обязателен"):
        Verification(
            result=result,
            explanation=VerificationExplanation(business_summary="   "),
        )


def test_rejects_aggregate_with_unknown_field() -> None:
    with pytest.raises(Exception, match="Extra inputs are not permitted"):
        Verification(
            result=VerificationResult.model_validate(contract_result()),
            explanation=VerificationExplanation(business_summary="сценарий"),
            model_auto_edited=False,  # type: ignore[call-arg]
        )


def test_verify_trace_rejects_state_missing_variable() -> None:
    model = BehavioralModel.model_validate(CASE_MODEL)
    document = deepcopy(COMPLETE_RESULT)
    del document["counterexample"]["steps"][1]["state"]["cancelled"]

    result = VerificationResult.model_validate(document)
    assert result.counterexample is not None
    errors = model.verify_trace(result.counterexample.steps)

    assert any("нет переменной 'cancelled'" in error for error in errors)


def test_verify_trace_rejects_contract_counterexample_incomplete_state() -> None:
    model = BehavioralModel.model_validate(contract_model_fixed())
    result = VerificationResult.model_validate(contract_result())

    assert result.counterexample is not None
    errors = model.verify_trace(result.counterexample.steps)

    assert any("нет переменной 'attempts'" in error for error in errors)


def test_verify_trace_rejects_state_with_extra_variable() -> None:
    model = BehavioralModel.model_validate(CASE_MODEL)
    document = deepcopy(COMPLETE_RESULT)
    document["counterexample"]["steps"][1]["state"]["stage"] = "Review"

    result = VerificationResult.model_validate(document)
    assert result.counterexample is not None
    errors = model.verify_trace(result.counterexample.steps)

    assert any("переменная 'stage', которой нет в модели" in error for error in errors)


def test_verify_trace_rejects_value_outside_domain() -> None:
    model = BehavioralModel.model_validate(CASE_MODEL)
    document = deepcopy(COMPLETE_RESULT)
    document["counterexample"]["steps"][1]["state"]["status"] = "Rejected"

    result = VerificationResult.model_validate(document)
    assert result.counterexample is not None
    errors = model.verify_trace(result.counterexample.steps)

    assert any("не входит в домен" in error for error in errors)


def _result_for_status(status: str) -> VerificationResult:
    if status == "PROPERTY_VIOLATED":
        return VerificationResult.model_validate(contract_result())
    return VerificationResult.model_validate(
        {
            "status": status,
            "property_id": None if status == "MODEL_INVALID" else "P2",
            "engine": "TLC",
        }
    )


def test_rejects_empty_engine() -> None:
    assert_rejected(
        VerificationResult,
        {"status": "PROPERTY_HOLDS", "property_id": "P1", "engine": ""},
        "at least 1 character",
    )


def test_rejects_violated_without_counterexample() -> None:
    assert_rejected(
        VerificationResult,
        {"status": "PROPERTY_VIOLATED", "property_id": "P1", "engine": "TLC"},
        "контрпример обязателен",
    )


@pytest.mark.parametrize("status", ALLOWED_STATUSES_WITHOUT_COUNTEREXAMPLE)
def test_rejects_counterexample_on_non_violating_status(status: str) -> None:
    document = {**CASE_RESULT_VIOLATED, "status": status}

    assert_rejected(
        VerificationResult,
        document,
        "контрпример допустим только при PROPERTY_VIOLATED",
    )


@pytest.mark.parametrize("status", ALLOWED_STATUSES_WITHOUT_COUNTEREXAMPLE)
def test_rejects_counterexample_on_timeout_like_status(status: str) -> None:
    document = {**CASE_RESULT_VIOLATED, "status": status}

    assert_rejected(
        VerificationResult,
        document,
        f"а не при {status}",
    )


def test_rejects_empty_counterexample_steps() -> None:
    document = {**CASE_RESULT_VIOLATED, "counterexample": {"steps": []}}

    assert_rejected(VerificationResult, document, "at least 1 item")


def test_rejects_trace_starting_from_step_one() -> None:
    document = {**CASE_RESULT_VIOLATED, "counterexample": {"steps": [_step(1), _step(2)]}}

    assert_rejected(VerificationResult, document, "не совпадает с позицией в трассе")


def test_rejects_trace_with_number_gap() -> None:
    document = {
        **CASE_RESULT_VIOLATED,
        "counterexample": {"steps": [_step(0), _step(1), _step(3)]},
    }

    assert_rejected(VerificationResult, document, "шаг 2: номер 3 не совпадает с позицией")


def test_rejects_initial_step_carrying_transition() -> None:
    document = {
        **CASE_RESULT_VIOLATED,
        "counterexample": {"steps": [_step(0, transition="Approve"), _step(1)]},
    }

    assert_rejected(VerificationResult, document, "шаг 0 — начальное состояние")


def test_rejects_later_step_without_transition() -> None:
    document = {
        **CASE_RESULT_VIOLATED,
        "counterexample": {
            "steps": [
                _step(0),
                {
                    "number": 1,
                    "state": {"status": "Approved", "approved": True, "cancelled": False},
                },
            ]
        },
    }

    assert_rejected(VerificationResult, document, "шаг 1 обязан называть переход")


def test_rejects_empty_state_in_step() -> None:
    document = {
        **CASE_RESULT_VIOLATED,
        "counterexample": {"steps": [_step(0, state={}), _step(1)]},
    }

    assert_rejected(VerificationResult, document, "at least 1 item")


def test_rejects_unknown_result_field() -> None:
    document = {**CASE_RESULT_VIOLATED, "auto_edited": False}

    assert_rejected(VerificationResult, document, "Extra inputs are not permitted")


def test_rejects_distinct_states_greater_than_generated() -> None:
    document = {
        "status": "PROPERTY_HOLDS",
        "property_id": "P1",
        "engine": "TLC",
        "statistics": {"states_generated": 10, "distinct_states": 37, "depth": 8},
    }

    assert_rejected(VerificationResult, document, "больше states_generated")


@pytest.mark.parametrize(
    "statistics",
    [
        {"states_generated": -1, "distinct_states": 0, "depth": 0},
        {"states_generated": 0, "distinct_states": -1, "depth": 0},
        {"states_generated": 0, "distinct_states": 0, "depth": -1},
    ],
)
def test_rejects_negative_statistics(statistics: dict[str, Any]) -> None:
    document = {
        "status": "PROPERTY_HOLDS",
        "property_id": "P1",
        "engine": "TLC",
        "statistics": statistics,
    }

    assert_rejected(VerificationResult, document, "greater than or equal to 0")


def test_rejects_unknown_statistics_field() -> None:
    document = {
        "status": "PROPERTY_HOLDS",
        "property_id": "P1",
        "engine": "TLC",
        "statistics": {
            "states_generated": 10,
            "distinct_states": 10,
            "depth": 2,
            "elapsed": "1s",
        },
    }

    assert_rejected(VerificationResult, document, "Extra inputs are not permitted")


def test_rejects_negative_duration() -> None:
    document = {**CASE_RESULT_VIOLATED, "duration_ms": -5}

    assert_rejected(VerificationResult, document, "greater than or equal to 0")


def _step(
    number: int, *, transition: str | None = None, state: dict[str, Any] | None = None
) -> dict[str, Any]:
    base = {
        0: {"status": "Created", "approved": False, "cancelled": False},
        1: {"status": "Approved", "approved": True, "cancelled": False},
        2: {"status": "Cancelled", "approved": True, "cancelled": True},
        3: {"status": "Executed", "approved": True, "cancelled": True},
    }
    step: dict[str, Any] = {
        "number": number,
        "state": state if state is not None else base.get(number, {}),
    }
    if transition is not None or number > 0:
        step["transition"] = transition if transition is not None else f"Step{number}"
    return step
