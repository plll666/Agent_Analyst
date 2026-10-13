from app.domain.behavioral_model import (
    BehavioralModel,
    Property,
    PropertyType,
    Transition,
    Variable,
)
from app.domain.expressions import AndExpr, Effect, EqExpr, InExpr, VarExpr
from app.domain.verification import (
    Verification,
    VerificationExplanation,
    VerificationResult,
)
from tests.domain.case_examples import (
    CASE_INITIAL,
    CASE_MODEL,
    CASE_PROPERTIES,
    CASE_RESULT_HOLDS,
    CASE_RESULT_VIOLATED,
    CASE_TRANSITION_APPROVE,
    CASE_TRANSITION_CANCEL,
    CASE_TRANSITION_EXECUTE,
    CASE_VARIABLES,
    COMPLETE_RESULT,
    CONTRACT_EXPLANATION,
    CONTRACT_MODEL_FIXED,
    CONTRACT_PENDING_RESULT,
    contract_model_fixed,
    contract_result,
    fixed_model,
)


def test_accepts_case_variables_block() -> None:
    variables = [Variable.model_validate(item) for item in CASE_VARIABLES]

    assert [variable.name for variable in variables] == [
        "status",
        "approved",
        "cancelled",
        "attempts",
    ]
    assert variables[0].values == ("Created", "Approved", "Cancelled", "Executed")
    assert variables[3].min == 0
    assert variables[3].max == 3


def test_accepts_case_initial_block() -> None:
    document = {
        "variables": CASE_VARIABLES,
        "initial": CASE_INITIAL,
        "transitions": [CASE_TRANSITION_APPROVE],
        "properties": [CASE_PROPERTIES[0]],
    }
    model = BehavioralModel.model_validate(document)

    assert model.initial == {
        "status": "Created",
        "approved": False,
        "cancelled": False,
        "attempts": 0,
    }
    assert isinstance(model.initial["attempts"], int)
    assert model.initial["approved"] is False


def test_accepts_case_transition_approve() -> None:
    transition = Transition.model_validate(CASE_TRANSITION_APPROVE)

    assert isinstance(transition.guard, EqExpr)
    assert transition.guard.op == "eq"
    assert len(transition.effects) == 2
    assert transition.effects[0].set == ("status", "Approved")
    assert transition.effects[1].set == ("approved", True)


def test_accepts_case_transition_cancel() -> None:
    transition = Transition.model_validate(CASE_TRANSITION_CANCEL)

    assert isinstance(transition.guard, InExpr)
    assert transition.guard.value == VarExpr(name="status")
    assert transition.guard.members == ["Created", "Approved"]


def test_accepts_case_transition_execute() -> None:
    transition = Transition.model_validate(CASE_TRANSITION_EXECUTE)

    assert isinstance(transition.guard, EqExpr)
    assert transition.guard.args[1] is True
    assert transition.effects[0].set == ("status", "Executed")


def test_accepts_case_property_deadlock_free_without_expression() -> None:
    prop = Property.model_validate({"id": "P4", "type": "deadlock_free"})

    assert prop.expression is None
    assert prop.type == "deadlock_free"


def test_accepts_all_four_property_types() -> None:
    types: list[PropertyType] = []
    for item in CASE_PROPERTIES:
        types.append(Property.model_validate(item).type)

    assert types == ["invariant", "forbidden_state", "reachable", "deadlock_free"]


def test_accepts_case_model_verbatim() -> None:
    model = BehavioralModel.model_validate(CASE_MODEL)

    assert len(model.variables) == 4
    assert [transition.name for transition in model.transitions] == [
        "Approve",
        "Cancel",
        "Execute",
    ]
    assert len(model.properties) == 4


def test_accepts_fixed_model_of_acceptance_test_two() -> None:
    model = BehavioralModel.model_validate(fixed_model())

    cancel = next(item for item in model.transitions if item.name == "Cancel")
    assert cancel.effects[2].set == ("approved", False)


def test_accepts_and_in_example_of_forbidden_state() -> None:
    model = BehavioralModel.model_validate(CASE_MODEL)

    forbidden = next(item for item in model.properties if item.id == "P2")
    assert isinstance(forbidden.expression, AndExpr)
    assert len(forbidden.expression.args) == 2


def test_accepts_every_dsl_operator_of_the_contract() -> None:
    document = contract_model_fixed()
    document["transitions"][0]["guard"] = {
        "and": [
            {"in": [{"var": "status"}, ["Created", "Approved"]]},
            {"eq": [{"var": "approved"}, False]},
        ]
    }
    model = BehavioralModel.model_validate(document)

    guard = model.transitions[0].guard
    assert isinstance(guard, AndExpr)
    assert isinstance(guard.args[0], InExpr)
    assert isinstance(guard.args[1], EqExpr)


def test_accepts_contract_model_of_section_8_2() -> None:
    document = contract_model_fixed()
    model = BehavioralModel.model_validate(document)

    assert [variable.name for variable in model.variables] == [
        "status",
        "approved",
        "attempts",
        "cancelled",
    ]
    assert model.transitions[0].source_reference == "p3"
    assert model.transitions[0].description is None


def test_accepts_description_on_variable_transition_and_property() -> None:
    document = contract_model_fixed()
    document["variables"][0]["description"] = "статус заявки"
    document["transitions"][0]["description"] = "согласование заявки"
    model = BehavioralModel.model_validate(document)

    assert model.variables[0].description == "статус заявки"
    assert model.transitions[0].description == "согласование заявки"
    assert model.properties[0].description == "Отменённую заявку исполнять нельзя"


def test_accepts_explicit_null_expression_of_contract() -> None:
    model = BehavioralModel.model_validate(contract_model_fixed())

    deadlock = next(item for item in model.properties if item.id == "P4")
    assert deadlock.type == "deadlock_free"
    assert deadlock.expression is None


def test_dump_omits_null_values_of_variable() -> None:
    dumped = BehavioralModel.model_validate(contract_model_fixed()).model_dump(mode="json")

    boolean = next(item for item in dumped["variables"] if item["name"] == "approved")
    assert "values" not in boolean
    assert "min" not in boolean
    assert "max" not in boolean


def test_dump_omits_null_expression_of_deadlock_free() -> None:
    dumped = BehavioralModel.model_validate(contract_model_fixed()).model_dump(mode="json")

    deadlock = next(item for item in dumped["properties"] if item["id"] == "P4")
    assert "expression" not in deadlock


def test_dump_omits_null_optional_fields_of_variable() -> None:
    dumped = BehavioralModel.model_validate(contract_model_fixed()).model_dump(mode="json")

    status = next(item for item in dumped["variables"] if item["name"] == "status")
    assert "description" not in status
    assert "source_reference" not in status


def test_verification_dumps_flat_for_frontend() -> None:
    verification = Verification(
        result=VerificationResult.model_validate(contract_result()),
        explanation=VerificationExplanation.model_validate(CONTRACT_EXPLANATION),
    )
    dumped = verification.model_dump(mode="json")

    assert "result" not in dumped
    assert "explanation" not in dumped
    assert dumped["status"] == "PROPERTY_VIOLATED"
    assert dumped["business_summary"] == CONTRACT_EXPLANATION["business_summary"]
    assert dumped["hypothesis"] == CONTRACT_EXPLANATION["hypothesis"]
    assert dumped["property_id"] == "P2"


def test_verification_dump_omits_null_fields() -> None:
    verification = Verification(
        result=VerificationResult.model_validate(CONTRACT_PENDING_RESULT),
        explanation=VerificationExplanation(business_summary=""),
    )
    dumped = verification.model_dump(mode="json")

    assert "property_id" not in dumped
    assert "counterexample" not in dumped
    assert "statistics" not in dumped
    assert dumped["business_summary"] == ""


def test_related_requirement_accepts_null_fields() -> None:
    result = VerificationResult.model_validate(
        {**contract_result(), "related_requirements": [{"paragraph_ref": None, "quote": None}]}
    )

    assert result.related_requirements is not None
    assert result.related_requirements[0].paragraph_ref is None
    assert result.related_requirements[0].quote is None


def test_accepts_names_of_reserved_tla_plus_words() -> None:
    document = {
        "variables": [
            {"name": "next", "type": "enum", "values": ["Created", "Cancelled"]},
            {"name": "default", "type": "boolean"},
            {"name": "module", "type": "boolean"},
        ],
        "initial": {"next": "Created", "default": False, "module": False},
        "transitions": [
            {
                "name": "then",
                "guard": {"eq": [{"var": "next"}, "Created"]},
                "effects": [{"set": ["default", True]}],
            }
        ],
        "properties": [
            {
                "id": "P1",
                "type": "invariant",
                "expression": {
                    "and": [
                        {"eq": [{"var": "next"}, "Cancelled"]},
                        {"eq": [{"var": "module"}, True]},
                    ]
                },
            }
        ],
    }

    model = BehavioralModel.model_validate(document)

    assert model.variables[0].name == "next"
    assert model.transitions[0].name == "then"


def test_round_trip_through_dump_is_stable() -> None:
    model = BehavioralModel.model_validate(CASE_MODEL)

    again = BehavioralModel.model_validate(model.model_dump(mode="json"))

    assert again == model


def test_round_trip_through_dump_is_stable_for_contract_model() -> None:
    model = BehavioralModel.model_validate(contract_model_fixed())

    again = BehavioralModel.model_validate(model.model_dump(mode="json"))

    assert again == model


def test_dump_keeps_case_wire_format() -> None:
    dumped = BehavioralModel.model_validate(CASE_MODEL).model_dump(mode="json")

    assert dumped["transitions"][0]["guard"] == {"eq": [{"var": "status"}, "Created"]}
    assert dumped["transitions"][1]["guard"] == {"in": [{"var": "status"}, ["Created", "Approved"]]}
    assert dumped["transitions"][2]["effects"] == [{"set": ["status", "Executed"]}]
    assert dumped["properties"][1]["expression"] == {
        "and": [
            {"eq": [{"var": "status"}, "Executed"]},
            {"eq": [{"var": "cancelled"}, True]},
        ]
    }


def test_effect_value_types_survive_round_trip() -> None:
    model = BehavioralModel.model_validate(CASE_MODEL)
    dumped = model.model_dump(mode="json")

    assert dumped["initial"]["approved"] is False
    assert dumped["initial"]["attempts"] == 0
    assert isinstance(dumped["initial"]["attempts"], int)
    assert dumped["transitions"][0]["effects"][1]["set"] == ["approved", True]


def test_json_schema_is_generated_for_llm_calls() -> None:
    schema = BehavioralModel.model_json_schema()

    assert "oneOf" in str(schema)
    assert "BehavioralModel" in str(schema)


def test_json_schema_lists_exactly_contract_operators() -> None:
    from app.domain.expressions import DSL_OPERATORS

    schema = str(BehavioralModel.model_json_schema())

    for operator in DSL_OPERATORS:
        assert f"'{operator}'" in schema
    for removed in ("'neq'", "'gt'", "'gte'", "'lt'", "'lte'", "'or'", "'not'"):
        assert removed not in schema


def test_verify_trace_accepts_consistent_trace() -> None:
    model = BehavioralModel.model_validate(CASE_MODEL)
    result = VerificationResult.model_validate(COMPLETE_RESULT)

    assert result.counterexample is not None
    assert model.verify_trace(result.counterexample.steps) == []


def test_verification_result_accepts_case_success_format() -> None:
    result = VerificationResult.model_validate(CASE_RESULT_HOLDS)

    assert result.status == "PROPERTY_HOLDS"
    assert result.property_id == "P1"
    assert result.engine == "TLC"
    assert result.statistics is not None
    assert result.statistics.states_generated == 162
    assert result.statistics.distinct_states == 37
    assert result.statistics.depth == 8
    assert result.counterexample is None


def test_verification_result_accepts_case_violation_format() -> None:
    result = VerificationResult.model_validate(CASE_RESULT_VIOLATED)

    assert result.status == "PROPERTY_VIOLATED"
    assert result.counterexample is not None
    steps = result.counterexample.steps
    assert len(steps) == 4
    assert steps[0].number == 0
    assert steps[0].transition is None
    assert [step.transition for step in steps[1:]] == ["Approve", "Cancel", "Execute"]
    assert steps[3].state["status"] == "Executed"
    assert steps[3].state["cancelled"] is True


def test_verification_result_accepts_contract_section_8_1() -> None:
    result = VerificationResult.model_validate(contract_result())

    assert result.status == "PROPERTY_VIOLATED"
    assert result.property_id == "P2"
    assert result.engine_version == "1.7.4"
    assert result.duration_ms == 812
    assert result.error_detail is None
    assert result.related_requirements is not None
    assert result.related_requirements[0].paragraph_ref == "p3"
    assert result.related_requirements[0].quote == "Заявка после согласования…"


def test_pending_result_without_property_id() -> None:
    result = VerificationResult.model_validate(CONTRACT_PENDING_RESULT)

    assert result.status == "PENDING"
    assert result.property_id is None
    assert result.counterexample is None


def test_pending_result_keeps_property_id_when_known() -> None:
    result = VerificationResult.model_validate({**CONTRACT_PENDING_RESULT, "property_id": "P2"})

    assert result.property_id == "P2"


def test_model_invalid_without_property_id() -> None:
    result = VerificationResult.model_validate(
        {"status": "MODEL_INVALID", "property_id": None, "engine": "TLC"}
    )

    assert result.property_id is None


def test_aggregate_accepts_contract_explanation() -> None:
    verification = Verification(
        result=VerificationResult.model_validate(contract_result()),
        explanation=VerificationExplanation.model_validate(CONTRACT_EXPLANATION),
    )

    assert verification.status == "PROPERTY_VIOLATED"
    assert verification.explanation.hypothesis == "гипотеза о причине"
    assert verification.explanation.question == "уточняющий вопрос"


def test_aggregate_accepts_pending_with_empty_summary() -> None:
    verification = Verification(
        result=VerificationResult.model_validate(CONTRACT_PENDING_RESULT),
        explanation=VerificationExplanation(business_summary=""),
    )

    assert verification.status == "PENDING"
    assert verification.explanation.business_summary == ""


def test_aggregate_accepts_terminal_without_hypothesis_and_question() -> None:
    verification = Verification(
        result=VerificationResult.model_validate(CASE_RESULT_HOLDS),
        explanation=VerificationExplanation(
            business_summary="Нарушений в исследованной модели не найдено"
        ),
    )

    assert verification.explanation.hypothesis is None
    assert verification.explanation.question is None


def test_effect_and_comparison_parse_into_expression_nodes() -> None:
    effect = Effect.model_validate({"set": ["status", "Approved"]})
    comparison = EqExpr.model_validate({"eq": [{"var": "attempts"}, 3]})

    assert effect.set == ("status", "Approved")
    assert comparison.args == [VarExpr(name="attempts"), 3]


def test_contract_model_fixture_matches_section_8_2() -> None:
    document = contract_model_fixed()

    assert document["transitions"][0]["source_reference"] == "p3"
    assert "description" in document["properties"][0]
    assert document["properties"][1] == {"id": "P4", "type": "deadlock_free", "expression": None}


def test_contract_model_fixed_differs_only_by_declared_variable() -> None:
    verbatim = contract_model_fixed()

    assert "cancelled" in [item["name"] for item in CONTRACT_MODEL_FIXED["variables"]]
    assert verbatim["initial"]["cancelled"] is False
