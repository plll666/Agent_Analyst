from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.expressions import (
    AndExpr,
    Effect,
    EqExpr,
    Expression,
    Ident,
    InExpr,
    Operand,
    Scalar,
    VarExpr,
)
from app.domain.verification import CounterexampleStep

VariableType = Literal["enum", "boolean", "integer"]

PropertyType = Literal["invariant", "forbidden_state", "reachable", "deadlock_free"]

EXPRESSION_REQUIRED_TYPES = frozenset({"invariant", "forbidden_state", "reachable"})

_VARIABLE_KIND: Mapping[VariableType, str] = {"enum": "str", "boolean": "bool", "integer": "int"}


class Variable(BaseModel):
    """Переменная состояния: ``values`` у ``enum``, ``min`` и ``max`` у ``integer``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Ident
    type: VariableType
    values: tuple[str, ...] | None = None
    min: int | None = None
    max: int | None = None
    description: str | None = None
    source_reference: str | None = None

    @model_validator(mode="after")
    def validate_domain(self) -> Variable:
        if self.type == "enum":
            if not self.values:
                raise ValueError(
                    f"переменная {self.name!r} типа enum требует непустой список values"
                )
            duplicates = [value for value, count in Counter(self.values).items() if count > 1]
            if duplicates:
                raise ValueError(
                    f"переменная {self.name!r}: значения домена повторяются: {sorted(duplicates)}"
                )
            if self.min is not None or self.max is not None:
                raise ValueError(
                    f"переменная {self.name!r} типа enum задаёт значения перечисления; "
                    "поля min и max к нему неприменимы"
                )
        elif self.type == "boolean":
            used = [name for name in ("values", "min", "max") if getattr(self, name) is not None]
            if used:
                raise ValueError(
                    f"переменная {self.name!r} типа boolean не принимает поля домена: {used}"
                )
        else:
            if self.values is not None:
                raise ValueError(
                    f"переменная {self.name!r} типа integer задаёт значения перечисления; "
                    "для целого положены границы min и max"
                )
            if self.min is None or self.max is None:
                raise ValueError(
                    f"переменная {self.name!r} типа integer требует обе границы min и max: "
                    "без них домен бесконечен и перебор состояний не завершится"
                )
            if self.min > self.max:
                raise ValueError(
                    f"переменная {self.name!r}: min={self.min} больше max={self.max}, домен пуст"
                )
        return self


class Property(BaseModel):
    """Проверяемое утверждение. Выражение обязательно у всех типов кроме ``deadlock_free``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Ident
    type: PropertyType
    expression: Expression | None = None
    description: str | None = None
    source_reference: str | None = None

    @model_validator(mode="after")
    def validate_expression(self) -> Property:
        needs_expression = self.type in EXPRESSION_REQUIRED_TYPES
        if needs_expression and self.expression is None:
            raise ValueError(f"свойство {self.id!r} типа {self.type!r} требует expression")
        if not needs_expression and self.expression is not None:
            raise ValueError(
                f"свойство {self.id!r} типа {self.type!r} выражается самим фактом проверки; "
                "поле expression к нему неприменимо"
            )
        return self


class Transition(BaseModel):
    """Одно допустимое изменение состояния: имя, guard и effects."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Ident
    guard: Expression
    effects: tuple[Effect, ...] = Field(min_length=1)
    description: str | None = None
    source_reference: str | None = None


class BehavioralModel(BaseModel):
    """Формальная модель состояний и переходов."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    variables: tuple[Variable, ...] = Field(min_length=1)
    initial: dict[str, Scalar] = Field(min_length=1)
    transitions: tuple[Transition, ...] = Field(min_length=1)
    properties: tuple[Property, ...] = Field(min_length=1)

    def variable_map(self) -> dict[str, Variable]:
        return {variable.name: variable for variable in self.variables}

    def verify_trace(self, steps: Sequence[CounterexampleStep]) -> list[str]:
        """Сверить состояния контрпримера с этой моделью: полнота и попадание в домены.

        Возвращает список нарушений, а не бросает: несоответствие состояния не отменяет
        прогон, а попадает в ``error_detail`` рядом с результатом.
        """
        variables = self.variable_map()
        expected = set(variables)
        errors: list[str] = []
        for step in steps:
            where = f"counterexample.steps[{step.number}]"
            for name in sorted(expected - set(step.state)):
                errors.append(f"{where}: в состоянии нет переменной {name!r}")
            for name in sorted(set(step.state) - expected):
                errors.append(
                    f"{where}: в состоянии есть переменная {name!r}, которой нет в модели"
                )
            for name in sorted(set(step.state) & expected):
                errors.extend(_value_errors(variables[name], step.state[name], where))
        return errors

    @model_validator(mode="after")
    def validate_model(self) -> BehavioralModel:
        """Собрать все нарушения и отвергнуть модель разом, а не по одному."""
        errors: list[str] = []
        variables: dict[str, Variable] = {}
        for variable in self.variables:
            if variable.name in variables:
                errors.append(f"variables: имя {variable.name!r} повторяется")
            else:
                variables[variable.name] = variable
        for label, names in (
            ("transitions", [transition.name for transition in self.transitions]),
            ("properties", [prop.id for prop in self.properties]),
        ):
            for name, count in Counter(names).items():
                if count > 1:
                    errors.append(f"{label}: имя {name!r} повторяется {count} раза")

        expected = set(variables)
        actual = set(self.initial)
        for missing in sorted(expected - actual):
            errors.append(f"initial: не задано начальное значение переменной {missing!r}")
        for unknown in sorted(actual - expected):
            errors.append(f"initial: ключ {unknown!r} не соответствует ни одной переменной модели")
        for name in sorted(actual & expected):
            errors.extend(_value_errors(variables[name], self.initial[name], f"initial.{name}"))

        for transition in self.transitions:
            path = f"transitions[{transition.name!r}]"
            errors.extend(_expression_errors(transition.guard, variables, f"{path}.guard"))
            assigned: set[str] = set()
            for index, effect in enumerate(transition.effects):
                target, value = effect.set
                where = f"{path}.effects[{index}]"
                if target not in variables:
                    errors.append(f"{where}: присваивание неизвестной переменной {target!r}")
                    continue
                if target in assigned:
                    errors.append(
                        f"{where}: переменная {target!r} уже присваивается в этом переходе, "
                        "результат двух присваиваний не определён"
                    )
                    continue
                assigned.add(target)
                errors.extend(_value_errors(variables[target], value, where))

        for prop in self.properties:
            if prop.expression is not None:
                errors.extend(
                    _expression_errors(
                        prop.expression, variables, f"properties[{prop.id!r}].expression"
                    )
                )

        if errors:
            raise ValueError("; ".join(errors))
        return self


def _literal_kind(value: Scalar) -> str:
    """Вид скаляра. Проверка bool раньше int: в Python ``bool`` — подтип ``int``."""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    return "str"


def _operand_kind(operand: Operand, variables: Mapping[str, Variable]) -> str:
    match operand:
        case VarExpr():
            return _VARIABLE_KIND[variables[operand.name].type]
        case _:
            return _literal_kind(cast(Scalar, operand))


def _value_errors(variable: Variable, value: Scalar, where: str) -> list[str]:
    match variable.type:
        case "enum":
            values = variable.values or ()
            if not isinstance(value, str):
                found = _literal_kind(value)
                return [f"{where}: {variable.name!r} типа enum ждёт строку, получено {found}"]
            if value not in values:
                return [
                    f"{where}: значение {value!r} не входит в домен "
                    f"{variable.name!r} = {list(values)}"
                ]
        case "boolean":
            if not isinstance(value, bool):
                found = _literal_kind(value)
                return [
                    f"{where}: {variable.name!r} типа boolean ждёт true/false, получено {found}"
                ]
        case _:
            if isinstance(value, bool) or not isinstance(value, int):
                found = _literal_kind(value)
                return [f"{where}: {variable.name!r} типа integer ждёт целое, получено {found}"]
            low, high = variable.min, variable.max
            if low is None or high is None:
                return [f"{where}: у {variable.name!r} типа integer не заданы границы домена"]
            if not low <= value <= high:
                return [
                    f"{where}: значение {value!r} вне диапазона {variable.name!r} = [{low}, {high}]"
                ]
    return []


def _domain_errors(
    operands: list[Operand], variables: Mapping[str, Variable], where: str
) -> list[str]:
    left, right = operands
    errors: list[str] = []
    for candidate, reference in ((left, right), (right, left)):
        if not isinstance(reference, VarExpr) or isinstance(candidate, VarExpr):
            continue
        variable = variables[reference.name]
        value = cast(Scalar, candidate)
        if (
            variable.type == "enum"
            and isinstance(value, str)
            and value not in (variable.values or ())
        ):
            errors.append(
                f"{where}: значение {value!r} не входит в домен {variable.name!r} "
                f"= {list(variable.values or ())}"
            )
    return errors


def _comparison_errors(expr: EqExpr, variables: Mapping[str, Variable], where: str) -> list[str]:
    """Проверить бинарное сравнение: известность операндов, типы и домены."""
    left, right = expr.args
    errors: list[str] = []
    for operand, label in ((left, "левый"), (right, "правый")):
        if isinstance(operand, VarExpr) and operand.name not in variables:
            errors.append(
                f"{where}: {label} операнд: ссылка на неизвестную переменную {operand.name!r}"
            )
    if errors:
        return errors

    left_kind = _operand_kind(left, variables)
    right_kind = _operand_kind(right, variables)
    if left_kind != right_kind:
        return [f"{where}: операнды разных типов: {left_kind} и {right_kind}"]
    return _domain_errors(expr.args, variables, where)


def _membership_errors(expr: InExpr, variables: Mapping[str, Variable], where: str) -> list[str]:
    if isinstance(expr.value, VarExpr) and expr.value.name not in variables:
        return [f"{where}: ссылка на неизвестную переменную {expr.value.name!r}"]
    errors: list[str] = []
    expected_kind = _operand_kind(expr.value, variables)
    for index, member in enumerate(expr.members):
        member_kind = _literal_kind(member)
        if member_kind != expected_kind:
            errors.append(
                f"{where}: элемент {index} списка типа {member_kind}, "
                f"а сравнивается {expected_kind}"
            )
            continue
        if isinstance(expr.value, VarExpr):
            errors.extend(
                _value_errors(
                    variables[expr.value.name], member, f"{where}: элемент {index} списка"
                )
            )
    return errors


def _expression_errors(
    expr: Expression, variables: Mapping[str, Variable], where: str
) -> list[str]:
    match expr:
        case VarExpr():
            if expr.name not in variables:
                return [f"{where}: ссылка на неизвестную переменную {expr.name!r}"]
        case AndExpr():
            errors: list[str] = []
            for index, operand in enumerate(expr.args):
                errors.extend(_expression_errors(operand, variables, f"{where}.and[{index}]"))
            return errors
        case InExpr():
            return _membership_errors(expr, variables, where)
        case EqExpr():
            return _comparison_errors(expr, variables, where)
    return []
