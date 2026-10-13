from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Discriminator,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    StringConstraints,
    model_serializer,
    model_validator,
)

VAR_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

DSL_OPERATORS = ("var", "and", "eq", "in")

RESERVED_NAMES = frozenset(
    {
        *DSL_OPERATORS,
        "add",
        "and",
        "as",
        "assert",
        "assume",
        "bool",
        "by",
        "case",
        "choose",
        "constant",
        "default",
        "definition",
        "do",
        "elif",
        "else",
        "end",
        "enum",
        "eq",
        "except",
        "exists",
        "extends",
        "false",
        "forall",
        "from",
        "gt",
        "gte",
        "if",
        "import",
        "in",
        "inc",
        "init",
        "instance",
        "lambda",
        "let",
        "lt",
        "lte",
        "module",
        "neq",
        "next",
        "none",
        "not",
        "or",
        "other",
        "pass",
        "raise",
        "return",
        "spec",
        "string",
        "subset",
        "then",
        "theorem",
        "true",
        "typeok",
        "unchanged",
        "union",
        "var",
        "variable",
        "variables",
        "while",
        "with",
        "yield",
    }
)

VarName = Annotated[str, StringConstraints(pattern=VAR_NAME_PATTERN.pattern)]


def _reject_reserved(value: str) -> str:
    if value.lower() in RESERVED_NAMES:
        raise ValueError(
            f"имя {value!r} зарезервировано: оно совпадает с оператором DSL, "
            "ключевым словом TLA+ или Python и не может быть именем элемента модели"
        )
    return value


Ident = Annotated[VarName, AfterValidator(_reject_reserved)]

Scalar = StrictStr | StrictBool | StrictInt

_INTERNAL_FIELDS = frozenset({"op", "name", "args", "value", "members"})

_WIRE_PAYLOAD_FIELD = {"var": "name", "and": "args", "eq": "args", "in": "in_args"}


def from_wire(value: Any) -> Any:
    """Привести одноключевой кейсовый вид выражения к теговому."""
    if not isinstance(value, Mapping):
        return value
    if "op" in value:
        return value
    if len(value) != 1:
        found = ", ".join(sorted(str(key) for key in value))
        raise ValueError(f"выражение задаётся одним ключом-оператором, а получено ключей: {found}")
    operator = next(iter(value))
    if operator in _INTERNAL_FIELDS:
        return value
    field = _WIRE_PAYLOAD_FIELD.get(operator)
    if field is None:
        allowed = ", ".join(DSL_OPERATORS)
        raise ValueError(f"неизвестный оператор {operator!r}; допустимые операторы: {allowed}")
    payload = value[operator]
    if operator == "in":
        if not isinstance(payload, (list, tuple)) or len(payload) != 2:
            raise ValueError(
                'оператор "in" ожидает два операнда: выражение и непустой список значений'
            )
        return {"op": operator, "value": payload[0], "members": payload[1]}
    return {"op": operator, field: payload}


class ExpressionBase(BaseModel):
    """Общее для узлов выражения: закрытый набор полей и неизменяемость."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="before")
    @classmethod
    def accept_wire_form(cls, value: Any) -> Any:
        return from_wire(value)


class VarExpr(ExpressionBase):
    """Ссылка на переменную состояния: ``{"var": "status"}``."""

    op: Literal["var"] = "var"
    name: Ident

    @model_serializer(mode="plain")
    def to_wire(self) -> dict[str, Any]:
        return {"var": self.name}


class AndExpr(ExpressionBase):
    """Конъюнкция: ``{"and": [выражение, выражение]}``."""

    op: Literal["and"] = "and"
    args: list[Expression] = Field(min_length=2)

    @model_serializer(mode="plain")
    def to_wire(self) -> dict[str, Any]:
        return {"and": self.args}


class EqExpr(ExpressionBase):
    """Равенство: ``{"eq": [{"var": "status"}, "Created"]}``. Ровно два операнда."""

    op: Literal["eq"] = "eq"
    args: list[Operand] = Field(min_length=2, max_length=2)

    @model_serializer(mode="plain")
    def to_wire(self) -> dict[str, Any]:
        return {"eq": self.args}


class InExpr(ExpressionBase):
    """Вхождение в множество: ``{"in": [{"var": "status"}, ["Created", "Approved"]]}``."""

    op: Literal["in"] = "in"
    value: Operand
    members: list[Scalar] = Field(min_length=1)

    @model_serializer(mode="plain")
    def to_wire(self) -> dict[str, Any]:
        return {"in": [self.value, self.members]}


Expression = Annotated[
    VarExpr | AndExpr | EqExpr | InExpr,
    Discriminator("op"),
    BeforeValidator(from_wire),
]

Operand = Expression | Scalar


class Effect(BaseModel):
    """Присваивание переменной: ``{"set": ["status", "Approved"]}``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    set: tuple[Ident, Scalar] = Field(min_length=2, max_length=2)


_EXPRESSION_NODES = (VarExpr, AndExpr, EqExpr, InExpr)


def _resolve_forward_references() -> None:
    namespace = {"Expression": Expression, "Operand": Operand, "Scalar": Scalar}
    for node in _EXPRESSION_NODES:
        node.model_rebuild(_types_namespace=namespace)


_resolve_forward_references()
