"""Этапы прогона: модель данных событий DAG и ядра.

Контракт спринта 3, раздел 5. Компоненты (агент и адаптер ядра) не знают про
БД и SSE: они получают асинхронный ``emit_stage(event)`` и отдают готовый
:class:`Stage`. Воркер добавляет идентичность прогона, присваивает ``seq``
и сохраняет.

Один этап начинается один раз и получает одно конечное состояние: это
проверяется :class:`StageRecorder` в воркере, а не здесь — здесь только форма.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.verification import Statistics


class StageScope(StrEnum):
    """Кто владеет этапом: агент или детерминированное ядро."""

    AGENT = "agent"
    CORE = "core"


class StageState(StrEnum):
    """Состояние этапа на текущий момент."""

    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


TERMINAL_STAGE_STATES: frozenset[StageState] = frozenset(
    {StageState.SUCCEEDED, StageState.FAILED, StageState.CANCELLED, StageState.SKIPPED}
)

AGENT_STAGE_NAMES = frozenset({"build", "gate", "check", "explain"})
CORE_STAGE_NAMES = frozenset({"validate", "compile_tla", "sany_check", "tlc_run", "parse_result"})


class Stage(BaseModel):
    """Снимок одного этапа — полный, как требует контракт.

    Attributes:
        stage_id: Уникален в прогоне; одинаков для начала, статистики и
            завершения одного этапа.
        parent_stage_id: Родительский этап либо ``None``; этапы ядра вложены в
            ``agent/check``.
        scope: ``agent`` или ``core``.
        name: Имя этапа из фиксированного набора своего scope.
        state: Текущее состояние.
        build_index: Ступень DAG, целое от 0.
        attempt: Попытка этапа, целое от 1.
        property_id: Проверяемое свойство либо ``None``, если этап общий.
        started_at: Начало этапа; обязательно для начатого этапа.
        finished_at: Завершение; заполнено у терминального состояния.
        duration_ms: Длительность; заполнена вместе с ``finished_at``.
        reason_code: Машинный код причины перестроения или ошибки.
        message: Короткое объяснение для пользователя, без секретов.
        statistics: Фактические показатели TLC, если получены.
    """

    model_config = ConfigDict(extra="forbid")

    stage_id: str = Field(min_length=1, max_length=128)
    parent_stage_id: str | None = Field(default=None, max_length=128)
    scope: StageScope
    name: str = Field(min_length=1, max_length=64)
    state: StageState
    build_index: int = Field(default=0, ge=0)
    attempt: int = Field(default=1, ge=1)
    property_id: str | None = Field(default=None, max_length=32)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    reason_code: str | None = Field(default=None, max_length=64)
    message: str | None = Field(default=None, max_length=2000)
    statistics: Statistics | None = None

    @model_validator(mode="after")
    def validate_stage(self) -> Stage:
        """Согласовать имя со scope и время со состоянием."""
        allowed = AGENT_STAGE_NAMES if self.scope is StageScope.AGENT else CORE_STAGE_NAMES
        if self.name not in allowed:
            raise ValueError(
                f"этап scope={self.scope} называется {self.name!r}, "
                f"допустимы: {', '.join(sorted(allowed))}"
            )
        if self.state is not StageState.SKIPPED and self.started_at is None:
            raise ValueError("начатый этап обязан иметь started_at")
        if self.state in TERMINAL_STAGE_STATES and self.state is not StageState.SKIPPED:
            if self.finished_at is None:
                raise ValueError(f"завершённый этап ({self.state}) обязан иметь finished_at")
            if self.duration_ms is None:
                raise ValueError(f"завершённый этап ({self.state}) обязан иметь duration_ms")
        if self.state is StageState.RUNNING and self.finished_at is not None:
            raise ValueError("у выполняющегося этапа не может быть finished_at")
        return self


# Типы событий контракта (раздел 5.2).
RUN_UPDATED = "run.updated"
STAGE_UPDATED = "stage.updated"
STAGE_STATISTICS = "stage.statistics"
AGENT_REBUILD = "agent.rebuild"
RUN_FINISHED = "run.finished"

EVENT_TYPES: frozenset[str] = frozenset(
    {RUN_UPDATED, STAGE_UPDATED, STAGE_STATISTICS, AGENT_REBUILD, RUN_FINISHED}
)

SCHEMA_VERSION = 1


class EventEnvelope(BaseModel):
    """Оболочка события SSE, обязательная для всех типов."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = SCHEMA_VERSION
    verification_id: str
    seq: int = Field(ge=0)
    occurred_at: datetime
    type: str
    data: dict[str, Any]

    @model_validator(mode="after")
    def validate_type(self) -> EventEnvelope:
        """Не пропускать события вне согласованного набора."""
        if self.type not in EVENT_TYPES:
            raise ValueError(f"неизвестный тип события: {self.type!r}")
        return self


def stage_event_data(stage: Stage) -> dict[str, Any]:
    """Полный снимок этапа для ``data`` события ``stage.updated``/``stage.statistics``."""
    return {"stage": stage.model_dump(mode="json")}
