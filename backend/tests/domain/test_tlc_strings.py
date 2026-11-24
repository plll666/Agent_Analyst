"""Строки модели сохраняют смысл после ASCII-кодирования для TLC."""

import pytest

from app.domain.tlc_output import parse_trace
from app.domain.tlc_strings import decode_string, encode_string


@pytest.mark.parametrize(
    "value",
    [
        "Created",
        "закончено с ошибкой",
        "закончено с ошибкой валидации",
        "Готово 🟢",
        "__aa_utf8_43616e63656c6c6564",
        "__aa_utf8_",
    ],
)
def test_round_trip_preserves_the_original_status(value: str) -> None:
    encoded = encode_string(value)

    assert encoded.isascii()
    assert decode_string(encoded) == value


def test_different_statuses_and_literal_prefix_do_not_collide() -> None:
    first = encode_string("закончено с ошибкой")
    second = encode_string("закончено с ошибкой валидации")

    assert first != second
    assert encode_string(first) != first
    assert decode_string(encode_string(first)) == first


def test_ascii_statuses_keep_the_existing_tla_representation() -> None:
    assert encode_string("Approved") == "Approved"


def test_counterexample_contains_original_statuses() -> None:
    start = "загрузка"
    error = "закончено с ошибкой валидации"
    trace = parse_trace(
        f'State 1: <Initial predicate>\nstatus = "{encode_string(start)}"\n'
        f'State 2: <ValidationFailed line 10, col 1>\nstatus = "{encode_string(error)}"\n'
    )

    assert trace is not None
    assert trace.steps[0].state["status"] == start
    assert trace.steps[1].state["status"] == error
    assert trace.steps[1].transition == "ValidationFailed"
