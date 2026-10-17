from dataclasses import dataclass
from typing import Final, Literal

from app.domain.behavioral_model import BehavioralModel, Property, Transition
from app.domain.expressions import (
    AndExpr,
    Effect,
    EqExpr,
    Expression,
    InExpr,
    Operand,
    Scalar,
    VarExpr,
)

MODULE_NAME: Final = "Model"
INDENT: Final = "  "
CONJUNCTION: Final = f"{INDENT}/\\ "


@dataclass(frozen=True, slots=True)
class CompiledSpec:
    """Готовые тексты спецификации и конфигурации TLC.

    Имя модуля внутри ``.tla`` обязано совпадать с именем файла, поэтому шаблон
    собирается под ``MODULE_NAME``, а не под имя вызывающего.

    ``polarity`` говорит, как читать вердикт движка. У ``reachable`` проверяется
    достижимость, и она выражается опровержением инварианта с отрицанием: если
    движок этот инвариант опроверг, требование выполнено. Без знака полярности
    адаптер сказал бы пользователю обратное.
    """

    tla: str
    cfg: str
    polarity: Literal["direct", "negated"] = "direct"


def compile_model(model: BehavioralModel, prop: Property) -> CompiledSpec:
    """Собрать спецификацию TLA+ и конфигурацию TLC для одного свойства.

    Одно свойство на спецификацию, а не все сразу: у ``VerificationResult`` одно
    поле ``property_id``, и при проверке пачки свойств невозможно честно сказать,
    какое именно сработало. Побочный выигрыш — прогон ограничен одним предикатом,
    поэтому таймаут и лимит состояний относятся к конкретному свойству.

    Args:
        model: Доменная модель прогона.
        prop: Проверяемое свойство, обязано принадлежать модели.

    Returns:
        Спецификация, конфигурация и полярность вердикта.

    Raises:
        KeyError: если ``prop`` не принадлежит ``model``.
    """
    if prop.id not in {known.id for known in model.properties}:
        raise KeyError(f"свойство {prop.id!r} не входит в модель")

    variables = ", ".join(variable.name for variable in model.variables)
    init = "\n".join(
        f"{CONJUNCTION}{variable.name} = {_literal(model.initial[variable.name])}"
        for variable in model.variables
    )
    transitions = "\n\n".join(_transition(model, transition) for transition in model.transitions)
    next_terms = "\n".join(f"{INDENT}\\/ {item.name}" for item in model.transitions)
    definition, cfg_directive, polarity = _property_definition(prop)

    lines = [
        f"{'-' * 28} MODULE {MODULE_NAME} {'-' * 28}",
        "EXTENDS Naturals, TLC",
        "",
        f"VARIABLES {variables}",
        "",
        "Init ==",
        init,
        "",
        transitions,
        "",
        "Next ==",
        next_terms,
        "",
        f"Spec == Init /\\ [][Next]_<<{variables}>>",
        "",
        definition,
        "",
        "=" * 71,
        "",
    ]
    cfg = "\n".join(["SPECIFICATION Spec", cfg_directive, ""])
    return CompiledSpec(tla="\n".join(lines), cfg=cfg, polarity=polarity)


def _transition(model: BehavioralModel, transition: Transition) -> str:
    r"""Один переход: гард плюс присваивание всех переменных без исключения.

    Присваиваются и те переменные, которых переход не касается: ``x' = x``.
    Без этого переменная остаётся в действии неопределённой, и результат
    перехода зависит от того, как TLC добрал остальные значения.
    """
    assigned = _assignments(transition.effects)
    body = [f"{CONJUNCTION}{term}" for term in _terms(transition.guard)]
    for variable in model.variables:
        if variable.name in assigned:
            body.append(f"{CONJUNCTION}{variable.name}' = {_literal(assigned[variable.name])}")
        else:
            body.append(f"{CONJUNCTION}{variable.name}' = {variable.name}")
    return "\n".join([f"{transition.name} ==", *body])


def _assignments(effects: tuple[Effect, ...]) -> dict[str, Scalar]:
    """Присваивания перехода по имени переменной.

    Модель запрещает повторное присваивание одной переменной в одном переходе,
    поэтому словарь не теряет ни одного эффекта.
    """
    return dict(effect.set for effect in effects)


def _property_definition(
    prop: Property,
) -> tuple[str, str, Literal["direct", "negated"]]:
    """Определение свойства в модуле, строка конфигурации и полярность вердикта.

    ``invariant`` и ``forbidden_state`` становятся инвариантами: запрещённое
    состояние это инвариант с отрицанием. ``deadlock_free`` — тоже инвариант над
    предикатом ``ENABLED Next``; собственный дедлок-отчёт TLC при этом подавлен
    флагом, чтобы один и тот же факт не приходил из двух источников.

    ``reachable`` проверяется отрицанием. Сказать «состояние достижимо» в TLC
    нельзя ни инвариантом, ни формулой ``<>P``: вторая требует достижимости на
    *каждом* поведении, а спецификация допускает вечное застывание в начальном
    состоянии, поэтому ``<>P`` опровергается всегда, что бы ни говорила модель.
    Зато «~P инвариант» истинно ровно тогда, когда P недостижимо, поэтому
    достижимость проверяется опровержением инварианта с отрицанием. Отсюда
    полярность ``negated``: вердикт движка по такому свойству читается наоборот.
    """
    match prop.type:
        case "invariant":
            return f"{prop.id} == {_predicate(prop.expression)}", f"INVARIANT {prop.id}", "direct"
        case "forbidden_state":
            return (
                f"{prop.id} == ~({_predicate(prop.expression)})",
                f"INVARIANT {prop.id}",
                "direct",
            )
        case "reachable":
            return (
                f"{prop.id} == ~({_predicate(prop.expression)})",
                f"INVARIANT {prop.id}",
                "negated",
            )
        case "deadlock_free":
            return f"{prop.id} == ENABLED Next", f"INVARIANT {prop.id}", "direct"
        case _:
            raise ValueError(f"неизвестный тип свойства {prop.type!r}")


def _predicate(expr: Expression | None) -> str:
    r"""Выражение в инфиксной форме с раскрытой конъюнкцией.

    ``and`` в домене — список операндов, а не бинарный узел, поэтому он
    разворачивается в цепочку ``/\``. Строка одна: предикат почти всегда входит
    в обёртку (``~(...)``), и многострочное тело внутри скобок выглядит как
    список аргументов, а не как утверждение.

    Args:
        expr: Выражение DSL либо ``None`` для типа свойства без выражения.

    Returns:
        Однострочное выражение TLA+.

    Raises:
        ValueError: если выражение не задано.
    """
    if expr is None:
        raise ValueError("свойство без выражения нельзя выразить предикатом")
    terms = _terms(expr)
    if len(terms) == 1:
        return terms[0]
    return " /\\ ".join(f"({term})" for term in terms)


def _terms(expr: Expression) -> list[str]:
    """Развернуть выражение в список конъюнктивных членов."""
    if isinstance(expr, AndExpr):
        terms: list[str] = []
        for operand in expr.args:
            terms.extend(_terms(operand))
        return terms
    return [_term(expr)]


def _term(expr: Expression) -> str:
    """Одно подвыражение без конъюнкции."""
    if isinstance(expr, VarExpr):
        return expr.name
    if isinstance(expr, AndExpr):
        return "(" + " /\\ ".join(_terms(expr)) + ")"
    if isinstance(expr, InExpr):
        members = ", ".join(_literal(member) for member in expr.members)
        return f"{_operand(expr.value)} \\in {{{members}}}"
    if isinstance(expr, EqExpr):
        left, right = expr.args
        return f"{_operand(left)} = {_operand(right)}"
    raise ValueError(f"выражение не компилируется в TLA+: {expr!r}")


def _operand(operand: Operand) -> str:
    if isinstance(operand, (VarExpr, AndExpr, InExpr, EqExpr)):
        return _term(operand)
    return _literal(operand)


def _literal(value: Scalar) -> str:
    """Скаляр DSL в литерале TLA+.

    ``bool`` проверяется раньше ``int``: в Python ``bool`` — подтип ``int``, иначе
    ``True`` превратился бы в ``1``, и равенство перестало бы быть сравнением с
    булевым операндом.
    """
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
