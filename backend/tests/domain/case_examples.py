from copy import deepcopy
from typing import Any

CASE_VARIABLES: list[dict[str, Any]] = [
    {
        "name": "status",
        "type": "enum",
        "values": ["Created", "Approved", "Cancelled", "Executed"],
    },
    {"name": "approved", "type": "boolean"},
    {"name": "cancelled", "type": "boolean"},
    {"name": "attempts", "type": "integer", "min": 0, "max": 3},
]

CASE_INITIAL: dict[str, Any] = {
    "status": "Created",
    "approved": False,
    "cancelled": False,
    "attempts": 0,
}

CASE_TRANSITION_APPROVE: dict[str, Any] = {
    "name": "Approve",
    "guard": {"eq": [{"var": "status"}, "Created"]},
    "effects": [
        {"set": ["status", "Approved"]},
        {"set": ["approved", True]},
    ],
}

CASE_TRANSITION_CANCEL: dict[str, Any] = {
    "name": "Cancel",
    "guard": {"in": [{"var": "status"}, ["Created", "Approved"]]},
    "effects": [
        {"set": ["status", "Cancelled"]},
        {"set": ["cancelled", True]},
    ],
}

CASE_TRANSITION_EXECUTE: dict[str, Any] = {
    "name": "Execute",
    "guard": {"eq": [{"var": "approved"}, True]},
    "effects": [{"set": ["status", "Executed"]}],
}

CASE_PROPERTY_INVARIANT: dict[str, Any] = {
    "id": "P1",
    "type": "invariant",
    "expression": {
        "and": [
            {"eq": [{"var": "status"}, "Cancelled"]},
            {"eq": [{"var": "cancelled"}, True]},
        ]
    },
}

CASE_PROPERTY_FORBIDDEN_STATE: dict[str, Any] = {
    "id": "P2",
    "type": "forbidden_state",
    "expression": {
        "and": [
            {"eq": [{"var": "status"}, "Executed"]},
            {"eq": [{"var": "cancelled"}, True]},
        ]
    },
}

CASE_PROPERTY_REACHABLE: dict[str, Any] = {
    "id": "P3",
    "type": "reachable",
    "expression": {"eq": [{"var": "status"}, "Executed"]},
}

CASE_PROPERTY_DEADLOCK_FREE: dict[str, Any] = {
    "id": "P4",
    "type": "deadlock_free",
}

CASE_TRANSITIONS: list[dict[str, Any]] = [
    CASE_TRANSITION_APPROVE,
    CASE_TRANSITION_CANCEL,
    CASE_TRANSITION_EXECUTE,
]

CASE_PROPERTIES: list[dict[str, Any]] = [
    CASE_PROPERTY_INVARIANT,
    CASE_PROPERTY_FORBIDDEN_STATE,
    CASE_PROPERTY_REACHABLE,
    CASE_PROPERTY_DEADLOCK_FREE,
]

CASE_MODEL: dict[str, Any] = {
    "variables": CASE_VARIABLES,
    "initial": CASE_INITIAL,
    "transitions": CASE_TRANSITIONS,
    "properties": CASE_PROPERTIES,
}

FIXED_CANCEL_EFFECTS: list[dict[str, Any]] = [
    {"set": ["status", "Cancelled"]},
    {"set": ["cancelled", True]},
    {"set": ["approved", False]},
]

CASE_RESULT_HOLDS: dict[str, Any] = {
    "status": "PROPERTY_HOLDS",
    "property_id": "P1",
    "engine": "TLC",
    "statistics": {
        "states_generated": 162,
        "distinct_states": 37,
        "depth": 8,
    },
}

CASE_RESULT_VIOLATED: dict[str, Any] = {
    "status": "PROPERTY_VIOLATED",
    "property_id": "P1",
    "engine": "TLC",
    "counterexample": {
        "steps": [
            {
                "number": 0,
                "state": {"status": "Created", "approved": False, "cancelled": False},
            },
            {
                "number": 1,
                "transition": "Approve",
                "state": {"status": "Approved", "approved": True, "cancelled": False},
            },
            {
                "number": 2,
                "transition": "Cancel",
                "state": {"status": "Cancelled", "approved": True, "cancelled": True},
            },
            {
                "number": 3,
                "transition": "Execute",
                "state": {"status": "Executed", "approved": True, "cancelled": True},
            },
        ]
    },
}

CONTRACT_MODEL: dict[str, Any] = {
    "variables": [
        {
            "name": "status",
            "type": "enum",
            "values": ["Created", "Approved", "Cancelled", "Executed"],
        },
        {"name": "approved", "type": "boolean"},
        {"name": "attempts", "type": "integer", "min": 0, "max": 3},
    ],
    "initial": {"status": "Created", "approved": False, "attempts": 0},
    "transitions": [
        {
            "name": "Approve",
            "guard": {"eq": [{"var": "status"}, "Created"]},
            "effects": [{"set": ["status", "Approved"]}, {"set": ["approved", True]}],
            "source_reference": "p3",
        }
    ],
    "properties": [
        {
            "id": "P2",
            "type": "forbidden_state",
            "expression": {
                "and": [
                    {"eq": [{"var": "status"}, "Executed"]},
                    {"eq": [{"var": "cancelled"}, True]},
                ]
            },
            "description": "Отменённую заявку исполнять нельзя",
        },
        {"id": "P4", "type": "deadlock_free", "expression": None},
    ],
}

CONTRACT_MODEL_FIXED: dict[str, Any] = {
    "variables": [
        *CONTRACT_MODEL["variables"],
        {"name": "cancelled", "type": "boolean"},
    ],
    "initial": {**CONTRACT_MODEL["initial"], "cancelled": False},
    "transitions": CONTRACT_MODEL["transitions"],
    "properties": CONTRACT_MODEL["properties"],
}

CONTRACT_COUNTEREXAMPLE: dict[str, Any] = {
    "steps": [
        {
            "number": 0,
            "transition": None,
            "state": {"status": "Created", "approved": False, "cancelled": False},
        },
        {
            "number": 1,
            "transition": "Approve",
            "state": {"status": "Approved", "approved": True, "cancelled": False},
        },
        {
            "number": 2,
            "transition": "Cancel",
            "state": {"status": "Cancelled", "approved": True, "cancelled": True},
        },
        {
            "number": 3,
            "transition": "Execute",
            "state": {"status": "Executed", "approved": True, "cancelled": True},
        },
    ]
}

CONTRACT_RESULT: dict[str, Any] = {
    "property_id": "P2",
    "status": "PROPERTY_VIOLATED",
    "engine": "TLC",
    "engine_version": "1.7.4",
    "statistics": {"states_generated": 162, "distinct_states": 37, "depth": 8},
    "counterexample": CONTRACT_COUNTEREXAMPLE,
    "related_requirements": [
        {"paragraph_ref": "p3", "quote": "Заявка после согласования…"},
    ],
    "duration_ms": 812,
    "error_detail": None,
}

CONTRACT_EXPLANATION: dict[str, Any] = {
    "business_summary": "текст сценария на языке требований",
    "hypothesis": "гипотеза о причине",
    "question": "уточняющий вопрос",
}

CONTRACT_PENDING_RESULT: dict[str, Any] = {
    "property_id": None,
    "status": "PENDING",
    "engine": "TLC",
}

COMPLETE_COUNTEREXAMPLE: dict[str, Any] = {
    "steps": [
        {
            "number": 0,
            "state": {
                "status": "Created",
                "approved": False,
                "cancelled": False,
                "attempts": 0,
            },
        },
        {
            "number": 1,
            "transition": "Approve",
            "state": {
                "status": "Approved",
                "approved": True,
                "cancelled": False,
                "attempts": 0,
            },
        },
        {
            "number": 2,
            "transition": "Cancel",
            "state": {
                "status": "Cancelled",
                "approved": True,
                "cancelled": True,
                "attempts": 0,
            },
        },
        {
            "number": 3,
            "transition": "Execute",
            "state": {
                "status": "Executed",
                "approved": True,
                "cancelled": True,
                "attempts": 0,
            },
        },
    ]
}

COMPLETE_RESULT: dict[str, Any] = {
    "property_id": "P2",
    "status": "PROPERTY_VIOLATED",
    "engine": "TLC",
    "counterexample": COMPLETE_COUNTEREXAMPLE,
}


def case_model() -> dict[str, Any]:
    """Свежая глубокая копия: тест, ломающий один блок, не влияет на остальные."""
    return deepcopy(CASE_MODEL)


def fixed_model() -> dict[str, Any]:
    """Модель acceptance-теста №2: ``Cancel`` сбрасывает ``approved``."""
    document = case_model()
    for transition in document["transitions"]:
        if transition["name"] == "Cancel":
            transition["effects"] = deepcopy(FIXED_CANCEL_EFFECTS)
    return document


def contract_model() -> dict[str, Any]:
    """Модель §8.2 контракта как напечатана: ``cancelled`` упомянута, но не объявлена."""
    return deepcopy(CONTRACT_MODEL)


def contract_model_fixed() -> dict[str, Any]:
    """Модель §8.2 контракта с объявленной переменной ``cancelled``."""
    return deepcopy(CONTRACT_MODEL_FIXED)


def contract_result() -> dict[str, Any]:
    """Результат проверки из §8.1 и §8.3 контракта."""
    return deepcopy(CONTRACT_RESULT)
