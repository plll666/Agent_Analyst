import re
from typing import Final

from app.domain.expressions import Scalar
from app.domain.verification import Counterexample, CounterexampleStep, Statistics

_STATE_HEADER: Final = re.compile(r"^State\s+\d+:\s*(?P<detail>.*)$")
_INITIAL_VIOLATION: Final = re.compile(
    r"^Error: Invariant (?P<property>\w+) is violated by the initial state:"
)
_ASSIGNMENT: Final = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<value>.+)$")
_GENERATED: Final = re.compile(r"(?P<value>[\d,]+) states generated")
_DISTINCT: Final = re.compile(r"(?P<value>[\d,]+) distinct states found")
_DEPTH: Final = re.compile(r"depth of the .* state graph search is (?P<value>\d+)")
_INITIAL_PREDICATE: Final = "Initial"
_STUTTERING: Final = "Stuttering"
_CONJUNCTION: Final = "/\\"


def parse_statistics(output: str) -> Statistics | None:
    """Счётчики перебора из вывода TLC.

    Возвращает ``None``, если хотя бы одно из трёх чисел не найдено: домен требует
    все поля сразу, а нули вместо неизвестных выглядели бы как «перебор ничего не
    нашёл» — то есть как успех там, где проверка не отчиталась.

    Args:
        output: Объединённый вывод TLC.

    Returns:
        Статистика либо ``None``, если вывод неполный.
    """
    generated = _last_number(_GENERATED, output)
    distinct = _last_number(_DISTINCT, output)
    depth = _last_number(_DEPTH, output)
    if generated is None or distinct is None or depth is None:
        return None
    if distinct > generated:
        return None
    return Statistics(states_generated=generated, distinct_states=distinct, depth=depth)


def parse_trace(output: str) -> Counterexample | None:
    r"""Восстановить контрпример из вывода TLC с именами переходов.

    Имя перехода лежит в заголовке состояния (``State 2: <Approve line 12 ...>``),
    а не в строках присваиваний: ``/\ status = "Approved"`` — это значение
    переменной, а не переход. Состояние ``Stuttering`` из ловушки темпоральной
    проверки состоянием трассы не является и в неё не попадает.

    Отдельный случай — ``Error: Invariant ... is violated by the initial state``:
    нарушение прямо в начальном состоянии, заголовков ``State N:`` у него нет, и
    состояние печатается строками ``/\ x = y``. Без его разбора инвариант,
    нарушаемый стартовым состоянием, читался бы как сбой движка.

    Инвариантный и темпоральный контрпримеры отличаются только префиксом ``/\``
    у присваиваний, поэтому разбор один на оба.

    Args:
        output: Объединённый вывод TLC.

    Returns:
        Контрпример либо ``None``, если трассу разобрать не удалось.

    Примечание:
        Правдоподобный путь «на всякий случай» подставлять нельзя: результат
        проверки — это значение, и выдуманный контрпример читался бы для
        пользователя как настоящий.
    """
    steps: list[CounterexampleStep] = []
    state: dict[str, Scalar] | None = None
    transition: str | None = None

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("Back to state"):
            break
        if _INITIAL_VIOLATION.search(line):
            steps.extend(_initial_state_violation(output))
            break
        header = _STATE_HEADER.match(line)
        if header is not None:
            if state:
                steps.append(
                    CounterexampleStep(number=len(steps), transition=transition, state=state)
                )
            detail = header.group("detail").strip()
            if detail == _STUTTERING:
                state, transition = None, None
                continue
            state, transition = {}, _action_name(detail)
            continue
        if state is None:
            continue
        for part in line.split(_CONJUNCTION):
            assignment = _ASSIGNMENT.match(part.strip())
            if assignment is not None:
                state[assignment.group("name")] = _value(assignment.group("value"))

    if state:
        steps.append(CounterexampleStep(number=len(steps), transition=transition, state=state))
    if not steps or any(not step.state for step in steps):
        return None
    return Counterexample(steps=tuple(steps))


def _initial_state_violation(output: str) -> list[CounterexampleStep]:
    """Начальное состояние из сообщения о нарушении стартовым состоянием.

    Args:
        output: Вывод TLC, в котором есть такая строка ошибки.

    Returns:
        Один шаг с начальным состоянием либо пустой список, если значения не нашли.
    """
    state: dict[str, Scalar] = {}
    collecting = False
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not collecting:
            collecting = _INITIAL_VIOLATION.search(line) is not None
            continue
        if not line:
            break
        for part in line.split(_CONJUNCTION):
            assignment = _ASSIGNMENT.match(part.strip())
            if assignment is not None:
                state[assignment.group("name")] = _value(assignment.group("value"))
    return [CounterexampleStep(number=0, state=state)] if state else []


def _action_name(detail: str) -> str | None:
    """Имя перехода, приведшего в состояние, из заголовка ``State N:``.

    Формат заголовка — ``<Approve line 12, col 1 to line 15, col 27 of module Model>``:
    имя операции стоит первым словом внутри угловых скобок. Начальное состояние
    помечено ``<Initial predicate>`` и перехода не имеет.

    Args:
        detail: Текст заголовка после ``State N:``.

    Returns:
        Имя перехода либо ``None`` для начального состояния и для заголовка, из
        которого имя извлечь не удалось.
    """
    if not detail.startswith("<"):
        return None
    inner = detail[1:].split(">")[0].split()
    if not inner or inner[0] == _INITIAL_PREDICATE:
        return None
    return inner[0]


def _last_number(pattern: re.Pattern[str], output: str) -> int | None:
    """Последнее совпадение счётчика в выводе.

    Берётся последнее, а не первое: TLC печатает прогресс по ходу перебора и
    итоговую строку в конце, а правильной является итоговая.

    Args:
        pattern: Регулярное выражение с группой ``value``.
        output: Объединённый вывод TLC.

    Returns:
        Число либо ``None``, если счётчик не встретился.
    """
    found = pattern.findall(output)
    if not found:
        return None
    return int(found[-1].replace(",", ""))


def _value(raw: str) -> Scalar:
    """Значение переменной из строки присваивания в выводе TLC.

    Args:
        raw: Текст справа от ``=``.

    Returns:
        Строка, ``bool`` или целое — то же значение, что лежит в домене.
    """
    text = raw.strip()
    if text.upper() in {"TRUE", "FALSE"}:
        return text.upper() == "TRUE"
    if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
        return text[1:-1]
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return text
