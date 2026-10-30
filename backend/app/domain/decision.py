"""Правило «Stop / Ask Rule»: что агент делает по итогам итерации.

Правило одно, и видно оно прямо из кейса: при нарушении у пользователя есть что
уточнять, поэтому агент задаёт вопрос и ждёт ответа — следующая итерация
начинается после него. В остальных случаях уточнять нечего: либо нарушений нет,
либо проверка не дала результата, и продолжать цикл незачем.

Исключение — нарушение, причиной которого объяснение назвало саму модель
(``AGENT_ERROR``). Спрашивать пользователя о таком нарушении не о чем: это не
вопрос к требованию, а ошибка интерпретации, которую агент обязан исправить сам.
Такой прогон останавливается без вопроса.

Отдельный модуль, а не функция в воркере: правило должно читаться и проверяться
без очереди, без БД и без сети.
"""

from enum import StrEnum

from app.domain.verification import RootCause, VerificationStatus


class AnalysisDecision(StrEnum):
    """Что агент делает по итогам итерации."""

    ASK = "ASK"
    STOP = "STOP"


def decide(
    status: VerificationStatus,
    root_cause: RootCause | None = None,
) -> AnalysisDecision:
    """Решить, спросить пользователя или остановиться.

    Args:
        status: Терминальный статус итерации.
        root_cause: Класс причины, если объяснение уже готово. При
            ``AGENT_ERROR`` вопрос пользователю не задаётся: модель ошиблась,
            и это не уточнение к требованию.

    Returns:
        Решение агента.

    Raises:
        ValueError: прогон ещё идёт — решение принимается по терминальному статусу.
    """
    if status is VerificationStatus.PENDING:
        raise ValueError("решение принимается по терминальному статусу, а прогон ещё идёт")
    if status is VerificationStatus.PROPERTY_VIOLATED:
        if root_cause is RootCause.AGENT_ERROR:
            return AnalysisDecision.STOP
        return AnalysisDecision.ASK
    return AnalysisDecision.STOP
