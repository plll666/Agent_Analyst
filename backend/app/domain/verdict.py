"""Сведение прогонов по свойствам модели в один результат проверки.

Модель может нести несколько свойств, а у прогона в БД одна строка и одно поле
``property_id``. Правило сводимости выбрано так, чтобы две ошибки не могли
выдать ложный успех.
"""

from collections.abc import Sequence

from app.domain.verification import Statistics, VerificationResult, VerificationStatus

FAILURE_PRECEDENCE: tuple[VerificationStatus, ...] = (
    VerificationStatus.MODEL_INVALID,
    VerificationStatus.TIMEOUT,
    VerificationStatus.STATE_LIMIT_REACHED,
    VerificationStatus.ENGINE_ERROR,
)


def combine(results: Sequence[VerificationResult]) -> VerificationResult:
    """Свести прогоны по всем свойствам модели в один результат проверки.

    Правило:

    1. Найденное нарушение важнее любой неудачи соседнего свойства. Если одно
       свойство опровергнуто, это уже результат проверки, и молчать о нём из-за
       таймаута другого свойства нельзя.
    2. Любая неудача важнее ``PROPERTY_HOLDS``. Свойство, которое не дочиталось,
       не проверено, поэтому «нарушений не нашлось» про него сказать нельзя.
    3. Порядок неудач зафиксирован, чтобы результат не зависел от порядка
       свойств в модели.

    Args:
        results: По одному результату на свойство, все для одной модели и одного
            прогона.

    Returns:
        Результат, который можно записать в строку ``verifications``. Поля
        ``counterexample``, ``statistics`` и ``property_id`` берутся из прогона,
        давшего выбранный статус.

    Raises:
        ValueError: если список пуст — у модели по контракту есть хотя бы одно
            свойство, и пустой набор означает, что модель до сюда не дошла.
    """
    if not results:
        raise ValueError("нечего сводить: ни одно свойство не проверено")

    violated = _first(results, VerificationStatus.PROPERTY_VIOLATED)
    if violated is not None:
        return violated

    for status in FAILURE_PRECEDENCE:
        failed = _first(results, status)
        if failed is not None:
            return failed

    holds = [result for result in results if result.status is VerificationStatus.PROPERTY_HOLDS]
    if len(holds) == len(results):
        return _sum_up_holds(holds)

    pending = _first(results, VerificationStatus.PENDING)
    if pending is not None:
        return pending
    raise ValueError(f"непредвиденный набор статусов: {[str(item.status) for item in results]}")


def _sum_up_holds(results: Sequence[VerificationResult]) -> VerificationResult:
    """Сложить результаты успешных прогонов в один.

    Статистики суммируются: каждая проверка перебирала состояния отдельно, и
    вместе они обследовали их объединение. ``property_id`` перечисляет все
    проверенные свойства, потому что успех относится к каждому из них, а не к
    одному конкретному.

    Args:
        results: Все результаты со статусом ``PROPERTY_HOLDS``, непустой список.

    Returns:
        Единый ``PROPERTY_HOLDS`` с суммой счётчиков и перечнем свойств.
    """
    first = results[0]
    seen = [item.statistics for item in results if item.statistics is not None]
    durations = [item.duration_ms for item in results if item.duration_ms is not None]

    return VerificationResult(
        status=VerificationStatus.PROPERTY_HOLDS,
        property_id=", ".join(item.property_id or "" for item in results),
        engine=first.engine,
        engine_version=first.engine_version,
        statistics=Statistics(
            states_generated=sum(item.states_generated for item in seen),
            distinct_states=sum(item.distinct_states for item in seen),
            depth=max((item.depth for item in seen), default=0),
        )
        if seen
        else None,
        duration_ms=sum(durations) if durations else None,
    )


def _first(
    results: Sequence[VerificationResult], status: VerificationStatus
) -> VerificationResult | None:
    """Первый результат с нужным статусом."""
    for result in results:
        if result.status is status:
            return result
    return None
