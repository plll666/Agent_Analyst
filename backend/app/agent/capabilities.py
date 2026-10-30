"""Умеет ли выбранная модель рассуждать до ответа.

Галочка «рассуждать» на фронте показывается только тогда, когда провайдер это
действительно умеет: иначе пользователь включал бы настройку, которая ничего не
меняет. Проверка делается один раз на процесс и кешируется.

Способ проверки — короткий пробный запрос, а не догадка по имени модели.
Сначала просим ``reasoning_effort=none``: провайдер, который такого параметра не
знает, отвечает 400. Затем просим ``reasoning_effort=high``: у рассуждающей
модели в ``usage.completion_tokens_details.reasoning_tokens`` появляются токены
рассуждений. Если токены есть и при ``none``, модель рассуждает всегда — галочка
бесполезна, и это тоже честно сообщается.

Переменная ``LLM_REASONING_SUPPORTED`` позволяет обойтись без пробы:
``true``/``false`` фиксируют ответ, ``auto`` (по умолчанию) включает проверку.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.agent.llm import LLMSettings

logger = logging.getLogger(__name__)

_PROBE_PROMPT = "Сколько будет 17 умножить на 23? Ответь одним числом."
_PROBE_MAX_TOKENS = 512
_CACHE_TTL_SECONDS = 600.0
_TRUE_VALUES = {"true", "1", "yes", "on"}
_FALSE_VALUES = {"false", "0", "no", "off"}


@dataclass(frozen=True, slots=True)
class ReasoningCapability:
    """Ответ на вопрос «можно ли включать рассуждения».

    ``available is None`` означает «проверить не удалось»: сеть недоступна или
    провайдер ответил невнятно. В этом случае галочку не показываем, но запуск
    анализа не ломаем — параметр просто не передаётся.
    """

    available: bool | None
    always_on: bool = False
    source: str = "unknown"
    detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Представление для API: без внутренних подробностей пробы."""
        return {
            "available": self.available,
            "always_on": self.always_on,
            "source": self.source,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class _ProbeAnswer:
    """Разобранный ответ пробы."""

    reasoning_tokens: int
    rejected: bool = False


_CACHE: dict[tuple[str, str, str], tuple[float, ReasoningCapability]] = {}


async def detect_reasoning(
    settings: LLMSettings,
    *,
    client: httpx.AsyncClient | None = None,
    use_cache: bool = True,
) -> ReasoningCapability:
    """Определить, поддерживает ли модель рассуждения.

    Args:
        settings: Настройки провайдера.
        client: HTTP-клиент для пробы; по умолчанию создаётся и закрывается здесь.
        use_cache: Брать готовый ответ из кеша процесса.

    Returns:
        Возможность включения рассуждений и способ, которым это выяснено.
    """
    if not settings.is_configured:
        return ReasoningCapability(False, source="not_configured", detail="LLM не настроена")

    forced = _forced_capability(settings.reasoning_supported)
    if forced is not None:
        return forced

    key = (settings.base_url, settings.model, settings.reasoning_supported)
    now = time.monotonic()
    if use_cache:
        cached = _CACHE.get(key)
        if cached is not None and cached[0] > now:
            return cached[1]

    own_client = client is None
    http = client or httpx.AsyncClient(timeout=min(10.0, settings.timeout_seconds))
    try:
        capability = await _probe(http, settings)
    except Exception as error:  # noqa: BLE001 - проба не должна ломать запуск анализа
        logger.warning("llm: не удалось проверить поддержку рассуждений: %s", error)
        capability = ReasoningCapability(
            None, source="probe_failed", detail=f"проверка не удалась: {error}"
        )
    finally:
        if own_client:
            await http.aclose()

    _CACHE[key] = (now + _CACHE_TTL_SECONDS, capability)
    return capability


def reset_cache() -> None:
    """Забыть результаты проверки (нужно тестам и смене настроек)."""
    _CACHE.clear()


def _forced_capability(value: str) -> ReasoningCapability | None:
    """Ответ из переменной окружения, если он задан явно."""
    if value in _TRUE_VALUES:
        return ReasoningCapability(True, source="env", detail="задано LLM_REASONING_SUPPORTED")
    if value in _FALSE_VALUES:
        return ReasoningCapability(False, source="env", detail="задано LLM_REASONING_SUPPORTED")
    return None


async def _probe(http: httpx.AsyncClient, settings: LLMSettings) -> ReasoningCapability:
    """Спросить провайдера дважды: без рассуждений и с ними."""
    without = await _ask(http, settings, "none")
    if without.rejected:
        return ReasoningCapability(
            False,
            source="probe",
            detail="провайдер не принимает reasoning_effort",
        )

    with_reasoning = await _ask(http, settings, "high")
    if with_reasoning.rejected:
        return ReasoningCapability(
            False,
            source="probe",
            detail="провайдер не принимает reasoning_effort",
        )
    if with_reasoning.reasoning_tokens <= 0:
        return ReasoningCapability(
            False,
            source="probe",
            detail="модель не возвращает рассуждений",
        )
    return ReasoningCapability(
        True,
        always_on=without.reasoning_tokens > 0,
        source="probe",
        detail=("рассуждения включены всегда" if without.reasoning_tokens > 0 else None),
    )


async def _ask(http: httpx.AsyncClient, settings: LLMSettings, effort: str) -> _ProbeAnswer:
    """Один пробный запрос; 400 на ``reasoning_effort`` — это отказ."""
    response = await http.post(
        f"{settings.base_url}/chat/completions",
        headers={"Authorization": f"Bearer {settings.api_key}"},
        json={
            "model": settings.model,
            "messages": [{"role": "user", "content": _PROBE_PROMPT}],
            "max_tokens": _PROBE_MAX_TOKENS,
            "temperature": 0,
            "reasoning_effort": effort,
        },
    )
    if response.status_code == 400 and "reasoning_effort" in response.text.lower():
        return _ProbeAnswer(0, rejected=True)
    response.raise_for_status()
    usage = response.json().get("usage") or {}
    details = usage.get("completion_tokens_details") or {}
    tokens = details.get("reasoning_tokens")
    return _ProbeAnswer(int(tokens) if isinstance(tokens, (int, float)) else 0)
