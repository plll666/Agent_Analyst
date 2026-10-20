"""Ворота перед движком: модель проверяется на честность, а не на красоту."""

from copy import deepcopy
from typing import Any

from app.agent.self_check import check
from app.domain.behavioral_model import BehavioralModel

REQUIREMENT = (
    "Заявка после согласования может быть исполнена. "
    "Пользователь может отменить заявку до исполнения."
)
QUOTE = "Заявка после согласования может быть исполнена"


def _document() -> dict[str, Any]:
    """Модель с цитатами: такой документ ворота пропускают."""
    return {
        "variables": [
            {
                "name": "status",
                "type": "enum",
                "values": ["Created", "Approved", "Executed"],
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


def _model(document: dict[str, Any] | None = None) -> BehavioralModel:
    return BehavioralModel.model_validate(document or _document())


def test_model_with_quotes_passes_the_gate() -> None:
    """Модель, у которой каждое правило подкреплено текстом, проверять можно."""
    assert check(_model(), REQUIREMENT) == []


def test_transition_without_quote_is_rejected() -> None:
    """Правило без ссылки на текст — это правило, которого в требовании нет."""
    document = _document()
    document["transitions"][0].pop("source_reference")

    problems = check(_model(document), REQUIREMENT)

    assert any("переход 'Approve'" in problem for problem in problems)


def test_fabricated_quote_is_rejected() -> None:
    """Цитата, которой нет в тексте, — выдумка агента."""
    document = _document()
    document["transitions"][0]["source_reference"] = "Заявка может быть оплачена"

    problems = check(_model(document), REQUIREMENT)

    assert any("переход 'Approve'" in problem for problem in problems)


def test_property_without_quote_is_rejected() -> None:
    """Свойство тоже правило: ссылка на текст обязательна."""
    document = _document()
    document["properties"][0].pop("source_reference")

    problems = check(_model(document), REQUIREMENT)

    assert any("свойство 'P1'" in problem for problem in problems)


def test_variable_may_have_no_quote() -> None:
    """Состояние могло быть и не названо в тексте — это не повод гонять агента."""
    document = _document()
    document["variables"][0].pop("source_reference")
    document["variables"][1].pop("source_reference")

    assert check(_model(document), REQUIREMENT) == []


def test_variable_with_fabricated_quote_is_rejected() -> None:
    """Выдуманная ссылка не лучше отсутствующей."""
    document = _document()
    document["variables"][0]["source_reference"] = "Заявка может быть оплачена"

    problems = check(_model(document), REQUIREMENT)

    assert any("переменная 'status'" in problem for problem in problems)


def test_property_that_ignores_behaviour_is_rejected() -> None:
    """Свойство про неизменяемую величину истинно всегда: успех ничего не значит."""
    document = _document()
    document["variables"].append(
        {"name": "attempts", "type": "integer", "min": 0, "max": 3, "source_reference": QUOTE}
    )
    document["initial"]["attempts"] = 0
    document["properties"] = [
        {
            "id": "P1",
            "type": "invariant",
            "expression": {"eq": [{"var": "attempts"}, 0]},
            "source_reference": QUOTE,
        }
    ]

    problems = check(_model(document), REQUIREMENT)

    assert any("не зависит от поведения" in problem for problem in problems)


def test_deadlock_free_property_is_not_called_trivial() -> None:
    """``deadlock_free`` выражается самим фактом проверки, а не выражением."""
    document = _document()
    document["properties"] = [{"id": "P1", "type": "deadlock_free", "source_reference": QUOTE}]

    assert check(_model(document), REQUIREMENT) == []


def test_quote_may_be_a_prefix_of_the_text() -> None:
    """Цитата может быть началом фразы — это всё ещё дословный фрагмент."""
    document = deepcopy(_document())
    document["transitions"][0]["source_reference"] = "Заявка после согласования"

    assert check(_model(document), REQUIREMENT) == []
