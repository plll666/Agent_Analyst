"""Модели ответа модели: тот формат, в котором LLM отвечает.

Ответ модели — внешние данные, и проверяются они этими моделями: Instructor
строит из них схему запроса и ими же разбирает ответ. Поэтому формат ответа и
формат проверки не могут разъехаться — правка модели здесь меняет и то, и другое.

Отличие от доменной модели одно, и оно только в записи: выражения различаются
тегом ``op``, а присваивание называет переменную и значение по именам. В домене
это объединение классов и пара ``{"set": [имя, значение]}``; тег делает выбор
ветки явным для модели, а не для читателя JSON.

Доменная проверка встроена в сами модели: ``to_domain`` строит доменный объект, а
``model_validator`` вызывает его сразу после разбора. Ошибка домена становится
ошибкой проверки ответа, и Instructor переспрашивает модель с её текстом.
"""

from __future__ import annotations

import re
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, ValidationInfo, model_validator

from app.agent.citations import MIN_QUOTE_LENGTH, quote_issue
from app.domain.behavioral_model import BehavioralModel
from app.domain.explanation import explanation_errors
from app.domain.verification import (
    RelatedRequirement,
    RootCause,
    VerificationExplanation,
    VerificationStatus,
)

WireScalar = str | bool | int

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

_TECHNICAL_WORDS = frozenset({"tlc", "tla", "sany", "invariant", "deadlock"})

_TECHNICAL_SNIPPETS = ("tla+", "инвариант", "дедлок")


class WireBase(BaseModel):
    """Общая основа моделей ответа: лишних полей нет, модель неизменяема."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class WireVarExpression(WireBase):
    """Ссылка на переменную состояния."""

    op: Literal["var"]
    name: str


class WireAndExpression(WireBase):
    """Конъюнкция выражений."""

    op: Literal["and"]
    args: list[WireExpression]


class WireEqExpression(WireBase):
    """Равенство двух операндов."""

    op: Literal["eq"]
    args: list[WireOperand] = Field(min_length=2, max_length=2)


class WireInExpression(WireBase):
    """Вхождение операнда в множество значений."""

    op: Literal["in"]
    value: WireOperand
    members: list[WireScalar] = Field(min_length=1)


WireExpression = WireVarExpression | WireAndExpression | WireEqExpression | WireInExpression
WireOperand = WireExpression | WireScalar

WireVarExpression.model_rebuild()
WireAndExpression.model_rebuild()
WireEqExpression.model_rebuild()
WireInExpression.model_rebuild()


class WireEffect(WireBase):
    """Присваивание переменной."""

    variable: str
    value: WireScalar


class WireVariable(WireBase):
    """Переменная состояния."""

    name: str
    type: Literal["enum", "boolean", "integer"]
    values: list[str] | None
    min: int | None
    max: int | None
    description: str | None
    source_reference: str | None


class WireTransition(WireBase):
    """Одно допустимое изменение состояния."""

    name: str
    guard: WireExpression
    effects: list[WireEffect] = Field(min_length=1)
    description: str | None
    source_reference: str | None


class WireProperty(WireBase):
    """Проверяемое утверждение."""

    id: str
    type: Literal["invariant", "forbidden_state", "reachable", "deadlock_free"]
    expression: WireExpression | None
    description: str | None
    source_reference: str | None


class WireModelDocument(WireBase):
    """Документ модели в том виде, в котором его отдаёт модель."""

    variables: list[WireVariable]
    initial: dict[str, WireScalar]
    transitions: list[WireTransition]
    properties: list[WireProperty]

    @model_validator(mode="after")
    def _check_domain(self) -> Self:
        """Проверить документ доменом: ссылки, домены, имена, присваивания."""
        self.to_domain()
        return self

    def to_domain(self) -> BehavioralModel:
        """Превратить ответ в доменную модель.

        Returns:
            Валидная модель: домены конечны, все ссылки разрешены.

        Raises:
            ValueError: документ не является корректной моделью; текст ошибки
                уходит модели на исправление.
        """
        try:
            return BehavioralModel.model_validate(
                {
                    "variables": [variable.model_dump() for variable in self.variables],
                    "initial": dict(self.initial),
                    "transitions": [
                        {
                            "name": transition.name,
                            "guard": transition.guard.model_dump(),
                            "effects": [
                                {"set": [effect.variable, effect.value]}
                                for effect in transition.effects
                            ],
                            "description": transition.description,
                            "source_reference": transition.source_reference,
                        }
                        for transition in self.transitions
                    ],
                    "properties": [
                        {
                            "id": prop.id,
                            "type": prop.type,
                            "expression": (
                                prop.expression.model_dump()
                                if prop.expression is not None
                                else None
                            ),
                            "description": prop.description,
                            "source_reference": prop.source_reference,
                        }
                        for prop in self.properties
                    ],
                }
            )
        except ValidationError as error:
            raise ValueError(str(error)) from error


class WireRelatedRequirement(WireBase):
    """Ссылка на фрагмент исходного требования."""

    paragraph_ref: str | None
    quote: str


class WireExplanation(WireBase):
    """Объяснение контрпримера на языке требований."""

    scenario: list[str] = Field(min_length=1)
    hypothesis: str
    root_cause: Literal["REQUIREMENT_ERROR", "AGENT_ERROR", "MISSING_RULE"]
    question: str
    related_requirements: list[WireRelatedRequirement]

    @model_validator(mode="after")
    def _check_trace_and_quotes(self, info: ValidationInfo) -> Self:
        """Проверить то, что видно только вместе с трассой и текстом требования."""
        self.to_explanation()
        context: dict[str, Any] = dict(info.context or {})
        steps = context.get("steps")
        if isinstance(steps, int) and steps and len(self.scenario) != steps:
            raise ValueError(
                f"в scenario {len(self.scenario)} предложений, а в трассе {steps} шагов: "
                "опиши ровно по одному предложению на шаг"
            )
        self._check_trace_events(context)
        self._check_business_language()
        requirement_text = context.get("requirement_text")
        if isinstance(requirement_text, str):
            for item in self.related_requirements:
                quote = item.quote.strip()
                if not quote:
                    continue
                issue = quote_issue(requirement_text, quote)
                if issue is not None:
                    raise ValueError(
                        f"цитата {quote!r}: {issue}. "
                        f"Приводи только дословные фрагменты не короче {MIN_QUOTE_LENGTH} символов "
                        "и не менее двух слов"
                    )
        return self

    def _check_trace_events(self, context: dict[str, Any]) -> None:
        """Событие, названное в сценарии, должно быть в трассе.

        Сценарий описывает шаги контрпримера, поэтому переход модели, которого
        в трассе нет, — выдуманное событие. Гипотеза может ссылаться на события
        модели вне трассы: это рассуждение о модели, а не пересказ шага.
        """
        names = context.get("transition_names")
        trace = context.get("trace_transitions")
        if not isinstance(names, list) or not isinstance(trace, list):
            return
        known = {str(name) for name in names}
        in_trace = {str(name).lower() for name in trace}
        for index, sentence in enumerate(self.scenario):
            for token in _IDENTIFIER.findall(sentence):
                if token in known and token.lower() not in in_trace:
                    raise ValueError(
                        f"scenario[{index}] упоминает переход {token!r}, которого нет в трассе: "
                        "называй только события из трассы и не придумывай новых"
                    )

    def _check_business_language(self) -> None:
        """Объяснение должно быть понятно без знания TLA+ и моделчекера."""
        texts = [("hypothesis", self.hypothesis), ("question", self.question)]
        texts.extend(("scenario", sentence) for sentence in self.scenario)
        for label, text in texts:
            term = _technical_term(text)
            if term is not None:
                raise ValueError(
                    f"{label} содержит технический термин {term!r}: объясняй на языке "
                    "бизнеса, без TLA+, TLC, SANY и инвариантов"
                )

    def to_explanation(self) -> tuple[VerificationExplanation, tuple[RelatedRequirement, ...]]:
        """Превратить ответ в доменное объяснение и ссылки на текст.

        Returns:
            Объяснение и цитаты из требования.

        Raises:
            ValueError: объяснение неполное или цитата пустая; текст ошибки уходит
                модели на исправление.
        """
        steps = [item.strip() for item in self.scenario]
        if any(not step for step in steps):
            raise ValueError("scenario содержит пустое предложение: опиши каждый шаг трассы")
        explanation = VerificationExplanation(
            business_summary="\n".join(steps),
            hypothesis=self.hypothesis.strip(),
            question=self.question.strip(),
            root_cause=RootCause(self.root_cause),
        )
        errors = explanation_errors(VerificationStatus.PROPERTY_VIOLATED, explanation)
        if errors:
            raise ValueError("; ".join(errors))
        related: list[RelatedRequirement] = []
        for item in self.related_requirements:
            quote = item.quote.strip()
            if not quote:
                raise ValueError("related_requirements[].quote пуст")
            related.append(RelatedRequirement(paragraph_ref=item.paragraph_ref, quote=quote))
        return explanation, tuple(related)


def _technical_term(text: str) -> str | None:
    """Найти термин моделчекера, непонятный без TLA+.

    Проверяются отдельные латинские слова и характерные обрывки: подстрочный
    поиск по всему тексту ловил бы «tla» внутри других слов.
    """
    lowered = text.lower()
    for snippet in _TECHNICAL_SNIPPETS:
        if snippet in lowered:
            return snippet
    tokens: list[str] = _IDENTIFIER.findall(text)
    for token in tokens:
        if token.lower() in _TECHNICAL_WORDS:
            return token
    return None
