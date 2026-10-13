"""VerificationResult — результат детерминированной проверки.

Формат контракта из кейса, уточнённый разделом 8.1 ``API_CONTRACT.md``. Статусов
шесть плюс ``PENDING``: первые шесть — выход движка, ``PENDING`` — состояние записи,
пока фоновая задача не завершилась. Разводить их в одном перечислении удобно: колонка
``verifications.status`` и модель не расходятся.

``TIMEOUT`` и ``STATE_LIMIT_REACHED`` нельзя выдать за успех, поэтому контрпример
разрешён только при ``PROPERTY_VIOLATED``: при остальных статусах его наличие —
ошибка, и модель её не пропускает.

Ресурс ``Verification`` из контракта шире результата проверки: к голове движка в нём
приклеен хвост агента — сценарий на языке требований, гипотеза и вопрос. Обе части
живут в домене, но в разных моделях, потому что граница LLM / движок проходит именно
между ними: результат на вход агента, объяснение на его выход.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.domain.expressions import Scalar

NonEmpty = Annotated[str, StringConstraints(min_length=1)]


class VerificationStatus(StrEnum):
    """Итог проверки.

    ``PROPERTY_HOLDS`` означает лишь, что в исследованной конечной модели при заданных
    ограничениях нарушений нет. Это не доказательство корректности production-системы,
    и агент обязан это оговаривать.
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
    """Сколько состояния породил перебор."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    states_generated: int = Field(ge=0)
    distinct_states: int = Field(ge=0)
    depth: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> Statistics:
        """Проверить, что разных состояний не больше, чем порождено.

        Returns:
            Статистику без изменений.

        Raises:
            ValueError: если distinct_states превышает states_generated.
        """
        if self.distinct_states > self.states_generated:
            raise ValueError(
                f"distinct_states={self.distinct_states} больше "
                f"states_generated={self.states_generated}: "
                "разных состояний не может оказаться больше, чем порождено"
            )
        return self


class CounterexampleStep(BaseModel):
    """Один шаг трассы: номер, имя перехода и полное состояние.

    На шаге 0 перехода нет — это начальное состояние, а не результат события.

    Состав состояния модель не сверяет: у неё нет доступа к ``BehavioralModel``, а
    пример контрпримера в кейсе перечисляет состояния не полностью. Полноту состояния
    проверяет ``BehavioralModel.verify_trace``, куда сходятся и модель, и результат.
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
        """Проверить нумерацию шагов и наличие переходов на всех шагах кроме нулевого.

        Returns:
            Контрпример без изменений.

        Raises:
            ValueError: если трасса не начинается с шага 0, нумерация сбита или
                начальное состояние помечено переходом.
        """
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
    """Выход Model Checker Tool: то, что агент читает на входе."""

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
        """Требовать ``property_id`` там, где проверялось конкретное свойство.

        Returns:
            Результат без изменений.

        Raises:
            ValueError: если ``property_id`` пуст при статусе, который называет
                проверяемое свойство.
        """
        if self.property_id is None and self.status in STATUSES_REQUIRING_PROPERTY_ID:
            raise ValueError(
                f"статус {self.status} называет проверяемое свойство, "
                "поэтому property_id обязателен"
            )
        return self

    @model_validator(mode="after")
    def validate_counterexample_presence(self) -> VerificationResult:
        """Привязать контрпример к статусу: только при нарушении, и обязательно.

        Returns:
            Результат без изменений.

        Raises:
            ValueError: если контрпример обязателен, но отсутствует, либо присутствует
                при статусе, который нарушением не является.
        """
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

    ``business_summary`` обязателен и при этом может быть пустым: у ещё идущего прогона
    объяснять нечего, и критерий 8.6.3 контракта требует именно пустую строку. Пустая
    строка на любом другом статусе — уже нарушение, но правило живёт в агрегате
    ``Verification``, потому что там известен статус.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    business_summary: str
    hypothesis: str | None = None
    question: str | None = None


class Verification(BaseModel):
    """Ресурс контракта: результат проверки и объяснение агента рядом.

    Идентичности записи здесь нет: ``id``, ``project_id``, ``model_version_id`` и
    ``created_at`` добавляет API-слой при сборке ответа из строки ``verifications``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    result: VerificationResult
    explanation: VerificationExplanation

    @property
    def status(self) -> VerificationStatus:
        """Статус проверки.

        Returns:
            Статус из результата — чтобы не доставать его вложенным обращением.
        """
        return self.result.status

    @model_validator(mode="after")
    def validate_explanation_present(self) -> Verification:
        """Требовать объяснение на всех статусах, кроме ещё идущего прогона.

        Критерии 8.6.7 и 8.6.8: у успеха и у всех четырёх «результата нет» сценарий
        непустой, иначе пользователь увидит пустую строку там, где ждал вывод.

        Returns:
            Агрегат без изменений.

        Raises:
            ValueError: если при терминальном статусе объяснение пустое.
        """
        pending = self.result.status is VerificationStatus.PENDING
        if not pending and not self.explanation.business_summary.strip():
            raise ValueError(
                f"business_summary обязателен при статусе {self.result.status}: "
                "агент обязан объяснить результат на языке требований"
            )
        return self
