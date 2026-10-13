from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.domain.expressions import Scalar

NonEmpty = Annotated[str, StringConstraints(min_length=1)]


class VerificationStatus(StrEnum):
    """Итог проверки.

    ``PROPERTY_HOLDS`` означает лишь, что в исследованной конечной модели нарушений нет,
    и агент обязан оговорить это пользователю.
    """

    PENDING = "PENDING"
    PROPERTY_HOLDS = "PROPERTY_HOLDS"
    PROPERTY_VIOLATED = "PROPERTY_VIOLATED"
    MODEL_INVALID = "MODEL_INVALID"
    TIMEOUT = "TIMEOUT"
    STATE_LIMIT_REACHED = "STATE_LIMIT_REACHED"
    ENGINE_ERROR = "ENGINE_ERROR"


STATUSES_REQUIRING_PROPERTY_ID = frozenset(
    {
        VerificationStatus.PROPERTY_HOLDS,
        VerificationStatus.PROPERTY_VIOLATED,
        VerificationStatus.TIMEOUT,
        VerificationStatus.STATE_LIMIT_REACHED,
        VerificationStatus.ENGINE_ERROR,
    }
)


class Statistics(BaseModel):
    """Сколько состояний породил перебор."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    states_generated: int = Field(ge=0)
    distinct_states: int = Field(ge=0)
    depth: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> Statistics:
        if self.distinct_states > self.states_generated:
            raise ValueError(
                f"distinct_states={self.distinct_states} больше "
                f"states_generated={self.states_generated}: "
                "разных состояний не может оказаться больше, чем порождено"
            )
        return self


class CounterexampleStep(BaseModel):
    """Шаг трассы: номер, имя перехода и состояние.

    На шаге 0 перехода нет — это начальное состояние. Состав состояния сверяет
    ``BehavioralModel.verify_trace``: у шага нет доступа к модели.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    number: int = Field(ge=0)
    transition: str | None = None
    state: dict[str, Scalar] = Field(min_length=1)


class Counterexample(BaseModel):
    """Путь от начального состояния до первого нарушения свойства."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    steps: tuple[CounterexampleStep, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_trace(self) -> Counterexample:
        for position, step in enumerate(self.steps):
            if step.number != position:
                raise ValueError(
                    f"шаг {position}: номер {step.number} не совпадает с позицией в трассе"
                )
            if position == 0 and step.transition is not None:
                raise ValueError(
                    f"шаг 0 — начальное состояние, переход {step.transition!r} в нём быть не должно"
                )
            if position > 0 and step.transition is None:
                raise ValueError(f"шаг {position} обязан называть переход, ведущий в это состояние")
        return self


class RelatedRequirement(BaseModel):
    """Ссылка на фрагмент исходного требования, с которым связан контрпример."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    paragraph_ref: NonEmpty
    quote: NonEmpty


class VerificationResult(BaseModel):
    """Выход Model Checker Tool."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: VerificationStatus
    property_id: NonEmpty | None = None
    engine: NonEmpty
    engine_version: str | None = None
    statistics: Statistics | None = None
    counterexample: Counterexample | None = None
    related_requirements: tuple[RelatedRequirement, ...] | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    error_detail: str | None = None

    @model_validator(mode="after")
    def validate_property_id(self) -> VerificationResult:
        if self.property_id is None and self.status in STATUSES_REQUIRING_PROPERTY_ID:
            raise ValueError(
                f"статус {self.status} называет проверяемое свойство, "
                "поэтому property_id обязателен"
            )
        return self

    @model_validator(mode="after")
    def validate_counterexample_presence(self) -> VerificationResult:
        violated = self.status is VerificationStatus.PROPERTY_VIOLATED
        if violated and self.counterexample is None:
            raise ValueError("при статусе PROPERTY_VIOLATED контрпример обязателен")
        if not violated and self.counterexample is not None:
            raise ValueError(
                f"контрпример допустим только при PROPERTY_VIOLATED, а не при {self.status}"
            )
        return self


class VerificationExplanation(BaseModel):
    """Выход агента: сценарий на языке требований, гипотеза и вопрос.

    ``business_summary`` может быть пустым у ещё идущего прогона. Пустая строка на
    терминальном статусе запрещена в ``Verification``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    business_summary: str
    hypothesis: str | None = None
    question: str | None = None


class Verification(BaseModel):
    """Ресурс контракта: результат проверки и объяснение агента.

    Идентичности записи нет — её добавляет API-слой при сборке ответа.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    result: VerificationResult
    explanation: VerificationExplanation

    @property
    def status(self) -> VerificationStatus:
        return self.result.status

    @model_validator(mode="after")
    def validate_explanation_present(self) -> Verification:
        pending = self.result.status is VerificationStatus.PENDING
        if not pending and not self.explanation.business_summary.strip():
            raise ValueError(
                f"business_summary обязателен при статусе {self.result.status}: "
                "агент обязан объяснить результат на языке требований"
            )
        return self
