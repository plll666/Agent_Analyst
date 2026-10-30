"""Правила объяснения результата проверки.

Объяснение пишет агент, но проверяются его границы здесь: домен не знает ни про
LLM, ни про БД, поэтому правила выражены как функции над уже собранными типами.
Так их можно проверить без сети и без Postgres.

Позитивное требование кейса — у нарушения есть сценарий, гипотеза и вопрос —
проверяется в момент, когда агент собирает объяснение
(:func:`explanation_errors`). В самом ресурсе ``Verification`` оно намеренно не
зашито: честный откат при недоступной LLM оставляет нарушение без гипотезы, и
такая строка должна читаться, а не падать при выдаче истории.
"""

from app.domain.verification import VerificationExplanation, VerificationStatus


def explanation_errors(
    status: VerificationStatus, explanation: VerificationExplanation
) -> list[str]:
    """Перечислить, чего не хватает объяснению при данном статусе.

    Args:
        status: Терминальный статус прогона.
        explanation: Объяснение, которое собирается записать агент.

    Returns:
        Список нарушений; пустой означает, что объяснение согласовано со статусом.
    """
    errors: list[str] = []
    violated = status is VerificationStatus.PROPERTY_VIOLATED

    if status is VerificationStatus.PENDING:
        return errors

    if not explanation.business_summary.strip():
        errors.append(f"business_summary обязателен при статусе {status}")

    if not violated:
        if explanation.hypothesis is not None:
            errors.append(f"гипотеза допустима только при нарушении свойства, а статус {status}")
        if explanation.question is not None:
            errors.append(f"вопрос допустим только при нарушении свойства, а статус {status}")
        if explanation.root_cause is not None:
            errors.append(f"класс причины допустим только при нарушении, а статус {status}")
        return errors

    if explanation.hypothesis is None or not explanation.hypothesis.strip():
        errors.append("при нарушении свойства гипотеза обязательна: без неё нечего обсуждать")
    if explanation.question is None or not explanation.question.strip():
        errors.append("при нарушении свойства обязателен уточняющий вопрос пользователю")
    if explanation.root_cause is None:
        errors.append("при нарушении свойства обязателен класс причины")
    return errors


SUMMARIES: dict[VerificationStatus, str] = {
    VerificationStatus.PROPERTY_HOLDS: (
        "В исследованной модели нарушений не нашлось. Это не доказательство "
        "корректности системы: проверена только построенная модель."
    ),
    VerificationStatus.PROPERTY_VIOLATED: (
        "Найден контрпример — последовательность, нарушающая проверяемое свойство."
    ),
    VerificationStatus.MODEL_INVALID: (
        "Модель не прошла валидацию или не компилируется в TLA+, перебор не начался."
    ),
    VerificationStatus.TIMEOUT: "Движок не уложился в лимит времени, проверка не завершена.",
    VerificationStatus.STATE_LIMIT_REACHED: (
        "Исчерпан лимит состояний, перебор остановлен до конца."
    ),
    VerificationStatus.ENGINE_ERROR: "Движок завершился с ошибкой, результата проверки нет.",
    VerificationStatus.AGENT_ERROR: (
        "Агент не смог построить модель по этому требованию, поэтому проверка не начиналась."
    ),
    VerificationStatus.PENDING: "Проверка ещё выполняется.",
}


def summary_for(status: VerificationStatus) -> str:
    """Шаблонное объяснение статуса на языке пользователя.

    Используется, когда объяснять нечего (нет нарушения) или когда агент не смог
    ответить. Пустая строка рядом с терминальным статусом читалась бы как «всё
    хорошо», поэтому текст есть у каждого статуса.

    Args:
        status: Статус прогона.

    Returns:
        Текст объяснения.
    """
    return SUMMARIES[status]
