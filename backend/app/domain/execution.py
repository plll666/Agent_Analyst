"""Состояние выполнения прогона — отдельно от его логического результата.

``status`` отвечает на вопрос «что показала проверка», ``execution_status`` — на
вопрос «что сейчас происходит с задачей». Они разведены, потому что отмена
пересекает оба: отменённый прогон имеет логический ``CANCELLED`` и
``execution_status = CANCELLED``, а пока отмена только принята —
``execution_status = CANCELLING`` при ещё живом ``status = PENDING``.

Контракт спринта 3, раздел 4: ``QUEUED``/``RUNNING``/``CANCELLING`` всегда
соответствуют ``status = PENDING``; ``COMPLETED`` — ``PROPERTY_HOLDS`` или
``PROPERTY_VIOLATED``; ``FAILED`` — один из статусов незавершённой проверки.
"""

from __future__ import annotations

from enum import StrEnum

from app.domain.verification import VerificationStatus


class ExecutionStatus(StrEnum):
    """Как сейчас идёт задача прогона."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    CANCELLING = "CANCELLING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


ACTIVE_EXECUTION_STATUSES: frozenset[ExecutionStatus] = frozenset(
    {ExecutionStatus.QUEUED, ExecutionStatus.RUNNING, ExecutionStatus.CANCELLING}
)

FINISHED_EXECUTION_STATUSES: frozenset[ExecutionStatus] = frozenset(
    {ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED}
)

# К какому execution_status приводит запись каждого логического статуса.
EXECUTION_BY_STATUS: dict[VerificationStatus, ExecutionStatus] = {
    VerificationStatus.PENDING: ExecutionStatus.QUEUED,
    VerificationStatus.PROPERTY_HOLDS: ExecutionStatus.COMPLETED,
    VerificationStatus.PROPERTY_VIOLATED: ExecutionStatus.COMPLETED,
    VerificationStatus.MODEL_INVALID: ExecutionStatus.FAILED,
    VerificationStatus.TIMEOUT: ExecutionStatus.FAILED,
    VerificationStatus.STATE_LIMIT_REACHED: ExecutionStatus.FAILED,
    VerificationStatus.ENGINE_ERROR: ExecutionStatus.FAILED,
    VerificationStatus.AGENT_ERROR: ExecutionStatus.FAILED,
    VerificationStatus.CANCELLED: ExecutionStatus.CANCELLED,
}


def execution_for(status: VerificationStatus) -> ExecutionStatus:
    """К какому состоянию выполнения приводит запись логического статуса.

    Args:
        status: Логический статус прогона.

    Returns:
        Состояние выполнения для колонки ``execution_status``.
    """
    return EXECUTION_BY_STATUS[status]
