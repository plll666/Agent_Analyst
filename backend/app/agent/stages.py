"""Обвязка событий этапов для агента: репортер и перестроения.

Форма события живёт в :mod:`app.domain.stages` — это общий контракт §5.1 для
агента и ядра. Здесь только то, что нужно графу: репортер, который помнит время
начала и считает длительность, и факт перестроения ``agent.rebuild``.

Почему перестроение — отдельный тип события: это не этап, а переход между
ступенями DAG. У него нет ни начала, ни конца, поэтому :class:`AgentRebuild`
передаётся тем же callback'ом, что и :class:`~app.domain.stages.Stage`.

Модуль ничего не знает про БД и SSE: событие получает вызывающая сторона.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Literal, Protocol

from pydantic import Field

from app.domain.base import WireModel
from app.domain.stages import Stage, StageScope, StageState
from app.domain.verification import Statistics

logger = logging.getLogger(__name__)

__all__ = [
    "AGENT_STAGE_NAMES",
    "CORE_STAGE_NAMES",
    "AgentEvent",
    "AgentRebuild",
    "REASON_CANCEL_REQUESTED",
    "REASON_CHECK_FAILED",
    "REASON_GATE_REJECTED",
    "REASON_INVALID_RESPONSE",
    "REASON_LLM_UNAVAILABLE",
    "REASON_MODEL_INTERPRETATION_ERROR",
    "REASON_TIMEOUT",
    "Stage",
    "StageEmitter",
    "StageName",
    "StageReporter",
    "StageScope",
    "StageState",
]

StageName = Literal[
    # Этапы агента (DAG анализа).
    "build",
    "gate",
    "check",
    "explain",
    # Этапы ядра (компилятор и модель).
    "validate",
    "compile_tla",
    "sany_check",
    "tlc_run",
    "parse_result",
]
"""Имя этапа из набора своего scope: агентского или ядерного."""

AGENT_STAGE_NAMES = frozenset({"build", "gate", "check", "explain"})
"""Имена этапов агента — как в контракте §5.1."""

CORE_STAGE_NAMES = frozenset({"validate", "compile_tla", "sany_check", "tlc_run", "parse_result"})
"""Имена этапов ядра — как в контракте §5.1."""

REASON_GATE_REJECTED = "GATE_REJECTED"
"""Модель не прошла ворота цитат."""

REASON_MODEL_INTERPRETATION_ERROR = "MODEL_INTERPRETATION_ERROR"
"""Объяснение признало причиной нарушения ошибку самой модели."""

REASON_TIMEOUT = "TIMEOUT"
"""Этап упёрся в отведённое время."""

REASON_CANCEL_REQUESTED = "CANCEL_REQUESTED"
"""Прогон отменён: этап не успел завершиться."""

REASON_LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
"""Провайдер недоступен или отказал в запросе."""

REASON_INVALID_RESPONSE = "INVALID_RESPONSE"
"""Модель не вернула пригодный ответ за отведённые попытки."""

REASON_CHECK_FAILED = "CHECK_FAILED"
"""Проверка свойства упала: движок или адаптер завершились исключением."""


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
        scope: StageScope = StageScope.AGENT,
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
            state=StageState.RUNNING,
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
        state: Literal["SUCCEEDED", "FAILED", "CANCELLED"],
        reason_code: str | None = None,
        message: str | None = None,
        statistics: Statistics | None = None,
    ) -> None:
        """Закрыть этап: у завершённого есть время конца и длительность.

        Повторное завершение игнорируется: один этап получает одно конечное
        состояние, и второе означало бы смену исхода задним числом.
        """
        started = self._started.pop(stage_id, None)
        if started is None:
            return
        await self._publish(
            started.model_copy(
                update={
                    "state": StageState(state),
                    "finished_at": datetime.now(UTC),
                    "duration_ms": self._duration_ms(started),
                    "reason_code": reason_code,
                    "message": message,
                    "statistics": statistics,
                }
            )
        )

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
        """Эмиттер, вкладывающий события ядра в указанный этап.

        Этапы ядра (``validate``, ``tlc_run`` и остальные) приходят от адаптера
        движка без родителя. Родителя знает граф, поэтому он подставляет
        ``parent_stage_id`` и ступень, а не заставляет ядро помнить про DAG.
        """
        parent = self._started.get(stage_id)

        async def emit(event: AgentEvent) -> None:
            if isinstance(event, Stage) and parent is not None:
                event = event.model_copy(
                    update={
                        "parent_stage_id": parent.stage_id,
                        "build_index": parent.build_index,
                    }
                )
            await self._publish(event)

        return emit

    async def _publish(self, event: AgentEvent) -> None:
        """Отправить событие наружу, не роняя прогон из-за наблюдаемости."""
        if self._emit is None:
            return
        try:
            await self._emit(event)
        except Exception as error:  # noqa: BLE001 - наблюдаемость не роняет прогон
            logger.warning("не удалось передать событие этапа: %s", error)

    @staticmethod
    def _duration_ms(stage: Stage) -> int:
        """Длительность этапа с момента старта."""
        started_at = stage.started_at
        if started_at is None:
            return 0
        return max(0, int((datetime.now(UTC) - started_at).total_seconds() * 1000))
