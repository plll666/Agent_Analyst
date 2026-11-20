"""События этапов: агент и ядро рассказывают, что происходит с прогоном.

Контракт спринта 3 (§5.1) задаёт внутренний интерфейс: агент получает
асинхронный callback ``emit_stage(event)`` и сообщает через него о началах,
завершениях и ошибках этапов. Ядро (адаптер Model Checker) получает такой же
callback и вкладывает свои этапы в ``agent/check``. Ни агент, ни ядро не пишут
в БД и не знают про SSE: сохранение и доставка — забота воркера и backend.

Модуль чистый: ни БД, ни сети, ни LLM. Событие — это снимок состояния этапа,
один и тот же ``stage_id`` живёт от начала до завершения, поэтому история
восстанавливается даже при потере части доставки.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Literal, Protocol, Self

from pydantic import Field, model_validator

from app.domain.base import WireModel
from app.domain.verification import Statistics

logger = logging.getLogger(__name__)

StageScope = Literal["agent", "core"]
"""Кто выполняет этап: сам агент или детерминированное ядро проверки."""

StageName = Literal[
    # Агент (DAG итерации).
    "build",
    "gate",
    "check",
    "explain",
    # Ядро (адаптер запуска проверки).
    "validate",
    "compile_tla",
    "sany_check",
    "tlc_run",
    "parse_result",
]
"""Имя этапа. У агента этапы итерации, у ядра — шаги одной проверки свойства."""

REASON_GATE_REJECTED = "GATE_REJECTED"
"""Ворота не пропустили модель: правила не подкреплены цитатами."""

REASON_MODEL_INTERPRETATION_ERROR = "MODEL_INTERPRETATION_ERROR"
"""Объяснение признало причиной нарушения саму модель — она перестраивается."""

REASON_TIMEOUT = "TIMEOUT"
"""Этап упёрся в лимит времени."""

REASON_CANCEL_REQUESTED = "CANCEL_REQUESTED"
"""Прогон отменён: запрос отмены принят до завершения этапа."""

REASON_LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
"""Провайдер недоступен или отказал в запросе."""

REASON_INVALID_RESPONSE = "INVALID_RESPONSE"
"""Модель не вернула пригодный ответ за отведённые попытки."""

REASON_CHECK_FAILED = "CHECK_FAILED"
"""Проверка свойства упала: движок или адаптер завершились исключением."""


class Stage(WireModel):
    """Снимок одного этапа прогона.

    Один этап начинается один раз и получает одно конечное состояние.
    Перестройка создаёт новый ``stage_id`` и увеличивает ``build_index``;
    повтор запроса к LLM — новую попытку ``attempt`` внутри того же этапа.

    ``SUCCEEDED`` у ``tlc_run`` означает успешное выполнение инструмента, а не
    ``PROPERTY_HOLDS``: найденное нарушение — тоже нормальный результат проверки.
    """

    stage_id: str
    parent_stage_id: str | None = None
    scope: StageScope
    name: StageName
    state: Literal["RUNNING", "SUCCEEDED", "FAILED", "CANCELLED", "SKIPPED"]
    build_index: int = Field(ge=0)
    attempt: int = Field(ge=1)
    property_id: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    reason_code: str | None = None
    message: str | None = None
    statistics: Statistics | None = None

    @model_validator(mode="after")
    def _validate_completion(self) -> Self:
        """Завершённый этап несёт время и длительность, начатый — ещё нет."""
        if self.state == "RUNNING":
            if self.finished_at is not None or self.duration_ms is not None:
                raise ValueError(
                    f"этап {self.name!r} ещё выполняется: "
                    "finished_at и duration_ms должны быть пусты"
                )
        elif self.state == "SKIPPED":
            return self
        elif self.finished_at is None or self.duration_ms is None:
            raise ValueError(
                f"этап {self.name!r} в состоянии {self.state} обязан заполнить "
                "finished_at и duration_ms"
            )
        return self


class AgentRebuild(WireModel):
    """Факт перестроения модели: с какой ступени на какую и почему.

    Перестройка — не этап, а переход: она не «выполняется», а случается между
    этапами. Поэтому у неё своя форма события (``agent.rebuild`` в SSE).
    """

    from_build_index: int = Field(ge=0)
    to_build_index: int = Field(ge=0)
    reason_code: str
    message: str | None = None
    occurred_at: datetime


AgentEvent = Stage | AgentRebuild
"""Событие, которое агент передаёт через ``emit_stage``."""


class StageEmitter(Protocol):
    """Куда агент сообщает о ходе прогона.

    Реализацию даёт вызывающая сторона (воркер): она добавляет иденчность
    прогона и сохраняет события. Агент не знает ни про БД, ни про SSE.
    """

    async def __call__(self, event: AgentEvent) -> None:
        """Принять событие этапа или перестроения."""
        ...


class StageReporter:
    """Собирает события этапов одного прогона и отправляет их эмиттеру.

    Один репортер на итерацию: он помнит время начала каждого этапа, считает
    длительность и следит, чтобы завершение относилось к начатому этапу.
    Когда эмиттера нет (например, в тестах без наблюдаемости), репортер молча
    ничего не делает — граф работает одинаково в обоих случаях.

    Сбой наблюдаемости не должен ломать прогон: исключение эмиттера гасится и
    попадает в лог. Сохранение событий — отдельная гарантия доставки backend.
    """

    def __init__(self, emit: StageEmitter | None = None) -> None:
        self._emit = emit
        self._started: dict[str, Stage] = {}

    @property
    def enabled(self) -> bool:
        """Передаются ли события дальше."""
        return self._emit is not None

    async def start(
        self,
        name: StageName,
        *,
        scope: StageScope = "agent",
        build_index: int = 0,
        attempt: int = 1,
        property_id: str | None = None,
        message: str | None = None,
    ) -> str:
        """Начать этап и сообщить о его старте.

        Returns:
            Идентификатор этапа для :meth:`finish`; пустая строка, если
            наблюдаемости нет.
        """
        if self._emit is None:
            return ""
        stage_id = uuid.uuid4().hex
        stage = Stage(
            stage_id=stage_id,
            scope=scope,
            name=name,
            state="RUNNING",
            build_index=build_index,
            attempt=attempt,
            property_id=property_id,
            started_at=datetime.now(UTC),
            message=message,
        )
        self._started[stage_id] = stage
        await self._publish(stage)
        return stage_id

    async def finish(
        self,
        stage_id: str,
        *,
        state: Literal["SUCCEEDED", "FAILED", "CANCELLED", "SKIPPED"],
        reason_code: str | None = None,
        message: str | None = None,
        statistics: Statistics | None = None,
    ) -> None:
        """Завершить начатый этап полным снимком состояния."""
        emit = self._emit
        if emit is None or not stage_id:
            return
        started = self._started.pop(stage_id, None)
        if started is None:
            logger.warning("завершение неизвестного этапа %s", stage_id)
            return
        finished_at = datetime.now(UTC)
        duration_ms = max(0, int((finished_at - started.started_at).total_seconds() * 1000))
        stage = started.model_copy(
            update={
                "state": state,
                "finished_at": finished_at,
                "duration_ms": duration_ms,
                "reason_code": reason_code,
                "message": message if message is not None else started.message,
                "statistics": statistics,
            }
        )
        await self._publish(stage)

    async def rebuild(
        self,
        *,
        from_build_index: int,
        to_build_index: int,
        reason_code: str,
        message: str | None = None,
    ) -> None:
        """Сообщить о перестроении модели между ступенями DAG."""
        if self._emit is None:
            return
        await self._publish(
            AgentRebuild(
                from_build_index=from_build_index,
                to_build_index=to_build_index,
                reason_code=reason_code,
                message=message,
                occurred_at=datetime.now(UTC),
            )
        )

    def child(self, stage_id: str) -> StageEmitter:
        """Эмиттер для вложенных этапов: дописывает родителя, если его нет.

        Через него адаптер ядра сообщает о своих этапах (``validate``,
        ``tlc_run`` и остальных), не зная идентификатора родительского
        ``agent/check``: граф подставляет его сам.
        """

        async def emit(event: AgentEvent) -> None:
            if isinstance(event, Stage) and event.parent_stage_id is None:
                event = event.model_copy(update={"parent_stage_id": stage_id})
            await self._publish(event)

        return emit

    async def _publish(self, event: AgentEvent) -> None:
        """Отправить событие эмиттеру, не ломая прогон при его сбое."""
        emit = self._emit
        if emit is None:
            return
        try:
            await emit(event)
        except Exception as error:  # noqa: BLE001
            logger.warning("не удалось передать событие этапа: %s", error)
