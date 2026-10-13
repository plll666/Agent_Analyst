import pytest

from app.domain.behavioral_model import BehavioralModel
from app.domain.expressions import (
    DSL_OPERATORS,
    AndExpr,
    Effect,
    EqExpr,
    InExpr,
    VarExpr,
)
from app.domain.verification import VerificationResult
from tests.domain.helpers import assert_rejected

REMOVED_OPERATORS = ["not", "or", "neq", "gt", "gte", "lt", "lte", "add", "inc"]


@pytest.mark.parametrize(
    ("wire", "node_type", "operator"),
    [
        ({"var": "status"}, VarExpr, "var"),
        ({"and": [{"var": "a"}, {"var": "b"}]}, AndExpr, "and"),
        ({"eq": [{"var": "a"}, 1]}, EqExpr, "eq"),
        ({"in": [{"var": "a"}, [1, 2]]}, InExpr, "in"),
    ],
)
def test_parses_every_contract_operator(wire: dict, node_type: type, operator: str) -> None:
    from app.domain.behavioral_model import Transition

    transition = Transition.model_validate(
        {"name": "T", "guard": wire, "effects": [{"set": ["a", 0]}]}
    )

    assert isinstance(transition.guard, node_type)
    assert transition.guard.op == operator


def test_dsl_operator_list_matches_contract() -> None:
    assert DSL_OPERATORS == ("var", "and", "eq", "in")


@pytest.mark.parametrize("operator", REMOVED_OPERATORS)
def test_rejects_removed_operator(operator: str) -> None:
    document = {
        "variables": [{"name": "status", "type": "enum", "values": ["Created"]}],
        "initial": {"status": "Created"},
        "transitions": [
            {
                "name": "T",
                "guard": {operator: [{"var": "status"}, "Created"]},
                "effects": [{"set": ["status", "Created"]}],
            }
        ],
        "properties": [{"id": "P1", "type": "reachable", "expression": {"var": "status"}}],
    }

    assert_rejected(BehavioralModel, document, f"неизвестный оператор {operator!r}")


def test_serializes_back_to_case_format() -> None:
    from app.domain.behavioral_model import Transition

    wire = {"eq": [{"var": "status"}, "Created"]}
    transition = Transition.model_validate(
        {"name": "Approve", "guard": wire, "effects": [{"set": ["status", "Approved"]}]}
    )

    assert transition.model_dump(mode="json")["guard"] == wire


def test_accepts_tagged_form_as_well() -> None:
    tagged = {"op": "eq", "args": [{"op": "var", "name": "status"}, "Created"]}

    comparison = EqExpr.model_validate(tagged)

    assert comparison.args == [VarExpr(name="status"), "Created"]
    assert comparison.model_dump(mode="json") == {"eq": [{"var": "status"}, "Created"]}


def test_round_trip_is_stable() -> None:
    wire = {
        "and": [
            {"eq": [{"var": "status"}, "Executed"]},
            {"in": [{"var": "approved"}, [True, False]]},
        ]
    }
    comparison = AndExpr.model_validate(wire)

    assert AndExpr.model_validate(comparison.model_dump(mode="json")) == comparison


def test_rejects_expression_that_is_not_an_object() -> None:
    assert_rejected(EqExpr, "eq", "Input should be a valid dictionary")


def test_rejects_unknown_field_inside_operator() -> None:
    assert_rejected(
        EqExpr,
        {"op": "eq", "args": [{"var": "a"}, 1], "strict": True},
        "Extra inputs are not permitted",
    )


def test_rejects_variable_reference_without_name() -> None:
    assert_rejected(VarExpr, {"op": "var"}, "Field required")


def test_rejects_empty_object_as_expression() -> None:
    assert_rejected(EqExpr, {}, "выражение задаётся одним ключом-оператором")


def test_rejects_in_with_three_operands() -> None:
    assert_rejected(InExpr, {"in": [{"var": "a"}, [1], 2]}, 'оператор "in" ожидает два операнда')


def test_effect_requires_exactly_two_items() -> None:
    assert_rejected(Effect, {"set": ["status"]}, "at least 2 items")


def test_effect_target_must_be_a_string() -> None:
    assert_rejected(Effect, {"set": [1, "Approved"]}, "Input should be a valid string")


def test_effect_rejects_unknown_operator() -> None:
    assert_rejected(Effect, {"increment": ["attempts", 1]}, "Extra inputs are not permitted")


def test_expression_does_not_leak_into_verification_result() -> None:
    result = VerificationResult.model_validate(
        {
            "status": "PROPERTY_HOLDS",
            "property_id": "P1",
            "engine": "TLC",
            "statistics": {"states_generated": 1, "distinct_states": 1, "depth": 0},
        }
    )

    assert result.statistics is not None
    assert result.statistics.distinct_states == 1
