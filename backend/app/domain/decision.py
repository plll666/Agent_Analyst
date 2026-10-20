"""Правило «Stop / Ask Rule»: что агент делает по итогам итерации.

Правило одно, и видно оно прямо из кейса: при нарушении у пользователя есть что
уточнять, поэтому агент задаёт вопрос и ждёт ответа — следующая итерация
начинается после него. В остальных случаях уточнять нечего: либо нарушений нет,
либо проверка не дала результата, и продолжать цикл незачем.

Отдельный модуль, а не функция в воркере: правило должно читаться и проверяться
без очереди, без БД и без сети.
"""

from enum import StrEnum

from app.domain.verification import VerificationStatus


class AnalysisDecision(StrEnum):
    """Что агент делает по итогам итерации."""

    ASK = "ASK"
    STOP = "STOP"


def decide(status: VerificationStatus) -> AnalysisDecision:
    """Решить, спросить пользователя или остановиться.

    Args:
        status: Терминальный статус итерации.

    Returns:
        Решение агента.

    Raises:
        ValueError: прогон ещё идёт — решение принимается по терминальному статусу.
    """
    if status is VerificationStatus.PENDING:
        raise ValueError("решение принимается по терминальному статусу, а прогон ещё идёт")
    if status is VerificationStatus.PROPERTY_VIOLATED:
        return AnalysisDecision.ASK
    return AnalysisDecision.STOP
