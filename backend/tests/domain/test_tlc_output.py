"""Разбор вывода TLC: статистика и контрпример.

Тесты чистые: ни Java, ни БД. Разбирается настоящий вывод TLC, потому что именно
на нём строится ``VerificationResult``, который увидит пользователь.
"""

import pytest

from app.domain.tlc_output import parse_statistics, parse_trace

INVIOLATION_OUTPUT = """\
TLC2 Version 2026.10.15.145915 (rev: 932d35e)
Running breadth-first search Model-Checking with 1 worker.
Error: Invariant P1 is violated.
Error: The behavior up to this point is:
State 1: <Initial predicate>
/\\ cancelled = FALSE
/\\ approved = FALSE
/\\ status = "Created"

State 2: <Approve line 12, col 3 to line 15, col 27 of module Model>
/\\ cancelled = FALSE
/\\ approved = TRUE
/\\ status = "Approved"

State 3: <Cancel line 18, col 3 to line 21, col 22 of module Model>
/\\ cancelled = TRUE
/\\ approved = TRUE
/\\ status = "Cancelled"

State 4: <Execute line 24, col 3 to line 27, col 27 of module Model>
/\\ cancelled = TRUE
/\\ approved = TRUE
/\\ status = "Executed"

4 states generated, 4 distinct states found, 0 states left on queue.
The depth of the complete state graph search is 4.
Finished in 01s at (2026-10-17 13:39:03)
"""

INITIAL_STATE_OUTPUT = """\
Error: Invariant P1 is violated by the initial state:
/\\ cancelled = FALSE
/\\ approved = FALSE
/\\ status = "Created"

Finished in 00s at (2026-10-17 13:39:03)
"""

TEMPORAL_OUTPUT = """\
TLC2 Version 2026.10.15.145915 (rev: 932d35e)
Error: Temporal property NEVER_EXECUTED was violated.

Error: The following behavior constitutes a counter-example:

State 1: <Initial predicate>
status = "Created"

State 2: <Approve line 10, col 3 to line 11, col 25 of module Model>
status = "Approved"

State 3: Stuttering
2 states generated, 2 distinct states found, 0 states left on queue.
The depth of the complete state graph search is 2.
"""

PROGRESS_LINE = (
    "Progress(20) at 2026-10-17 13:29:42: 1234 states generated, "
    "999 distinct states found, 7 states left on queue.\n"
)
DEPTH_LINE = "The depth of the complete state graph search is 4.\n"


def test_reads_three_counters_from_the_final_line() -> None:
    """Все три счётчика берутся из итоговой строки, а не склеиваются в одно число."""
    statistics = parse_statistics(INVIOLATION_OUTPUT)

    assert statistics is not None
    assert statistics.states_generated == 4
    assert statistics.distinct_states == 4
    assert statistics.depth == 4


def test_keeps_only_the_last_progress_value() -> None:
    """TLC печатает прогресс по ходу: правильная последняя строка, а не первая."""
    statistics = parse_statistics(PROGRESS_LINE + INVIOLATION_OUTPUT)

    assert statistics is not None
    assert statistics.states_generated == 4
    assert statistics.distinct_states == 4


def test_returns_nothing_when_a_counter_is_missing() -> None:
    """Нулями вместо неизвестных подставиться нельзя: это выглядит как «перебор пуст»."""
    assert parse_statistics("Finished in 01s") is None


def test_recovers_transition_names_from_state_headers() -> None:
    """Имя перехода лежит в заголовке состояния, а не в строках присваиваний."""
    counterexample = parse_trace(INVIOLATION_OUTPUT)

    assert counterexample is not None
    assert [step.transition for step in counterexample.steps] == [
        None,
        "Approve",
        "Cancel",
        "Execute",
    ]


def test_reads_types_of_state_values() -> None:
    """Строки, булевы и целые разбираются в их настоящие типы, а не в текст."""
    counterexample = parse_trace(INVIOLATION_OUTPUT)

    assert counterexample is not None
    assert counterexample.steps[0].state == {
        "cancelled": False,
        "approved": False,
        "status": "Created",
    }
    assert counterexample.steps[3].state["approved"] is True
    assert counterexample.steps[3].state["status"] == "Executed"


def test_reads_violation_of_the_initial_state() -> None:
    """Нарушение стартовым состоянием идёт без заголовков ``State N:``.

    Если его не разобрать, инвариант, неверный уже в начальном состоянии, читается
    как сбой движка, а это обычный и полезный результат.
    """
    counterexample = parse_trace(INITIAL_STATE_OUTPUT)

    assert counterexample is not None
    assert [step.number for step in counterexample.steps] == [0]
    assert counterexample.steps[0].transition is None
    assert counterexample.steps[0].state == {
        "cancelled": False,
        "approved": False,
        "status": "Created",
    }


def test_reads_temporal_trace_without_conjunction_prefix() -> None:
    r"""Темпоральный контрпример пишется без ``/\`` — разбор один на оба вида."""
    counterexample = parse_trace(TEMPORAL_OUTPUT)

    assert counterexample is not None
    assert [step.transition for step in counterexample.steps] == [None, "Approve"]


def test_drops_stuttering_state_from_the_lasso() -> None:
    """Состояние ``Stuttering`` не состояние модели и в трассу не попадает."""
    counterexample = parse_trace(TEMPORAL_OUTPUT)

    assert counterexample is not None
    assert len(counterexample.steps) == 2


def test_returns_nothing_when_there_is_no_trace() -> None:
    """Нет трассы — нет контрпримера.

    Правдоподобный путь «на всякий случай» здесь выглядел бы для пользователя как
    настоящий контрпример, и это худший вид ложного успеха.
    """
    assert parse_trace("Model checking completed. No error has been found.") is None


def test_returns_nothing_when_a_state_has_no_assignments() -> None:
    """Состояние без значений переменных не годится: читать его нечего."""
    output = (
        "State 1: <Initial predicate>\n"
        "State 2: <Approve line 1, col 1 to line 2, col 1 of module Model>\n"
    )

    assert parse_trace(output) is None


@pytest.mark.parametrize(
    ("line", "generated", "distinct"),
    [
        ("Progress(2) at 2026-10-17 13:29:42: 12 states generated, 8 distinct states found", 12, 8),
        ("1,234 states generated, 999 distinct states found", 1234, 999),
        ("7 states generated, 7 distinct states found", 7, 7),
    ],
)
def test_reads_one_counter_without_concatenating_digits(
    line: str, generated: int, distinct: int
) -> None:
    """В строке прогресса несколько чисел: берётся нужное, а не склейка всех.

    Соседние счётчики — тоже числа: без разбора по названию в счётчик попала бы
    склейка ``12348`` вместо порождённых ``1234`` и различных ``8``.
    """
    statistics = parse_statistics(line + "\n" + DEPTH_LINE)

    assert statistics is not None
    assert statistics.states_generated == generated
    assert statistics.distinct_states == distinct


def test_returns_nothing_when_progress_has_no_depth() -> None:
    """Строка прогресса без итоговой глубины не даёт полной статистики."""
    assert parse_statistics(PROGRESS_LINE) is None
