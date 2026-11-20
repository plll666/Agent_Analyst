"""Профиль генерации: при каких настройках получен результат.

Задание спринта (А7) требует фиксировать для прогона версии промптов,
идентификатор модели LLM и фактические параметры генерации, включая режим
рассуждений. Эти данные входят в ключ повторного использования результата на
backend (контракт §3.1), поэтому профиль собирается в один объект, который
можно сохранить и посчитать от него отпечаток.

Профиль не содержит секретов: ключ провайдера и заголовки в него не попадают.
В «идентификатор конфигурации провайдера» входит адрес шлюза и режим
структурированного ответа — они влияют на результат, но секретами не являются.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from app.agent.llm import LLMSettings
from app.agent.prompts import EXPLANATION_PROMPT_VERSION, MODELING_PROMPT_VERSION
from app.domain.behavioral_model import SCHEMA_VERSION

AGENT_LOGIC_VERSION = "agent-2026-11-20.1"
"""Версия логики агента: схема DAG, правила ворот и критерии причин.

Меняется вместе с поведением графа, а не с текстом промптов: промпты имеют
свои версии, логика — свою. Обе входят в ключ повторного использования.
"""


@dataclass(frozen=True, slots=True)
class GenerationProfile:
    """Настройки, при которых агент построил модель и объяснение.

    Attributes:
        model_schema_version: Версия схемы ``BehavioralModel``.
        agent_logic_version: Версия логики агента (граф, ворота, критерии).
        modeling_prompt_version: Версия промпта построения модели.
        explanation_prompt_version: Версия промпта объяснения контрпримера.
        build_attempts: Бюджет попыток модели на один документ.
        max_rebuilds: Лимит перестроений модели.
        explanation_attempts: Бюджет попыток объяснения.
        llm_model: Идентификатор модели у провайдера.
        llm_provider: Адрес шлюза провайдера (без ключа).
        llm_structured_mode: Режим структурированного ответа.
        llm_temperature: Температура генерации (фиксирована нулём).
        llm_reasoning_effort: Уровень рассуждений из настроек провайдера.
        llm_reasoning_mode: Фактический режим: ``provider_default``,
            ``enabled:<effort>`` или ``disabled``.
        llm_max_attempts: Бюджет попыток пригодного ответа у клиента LLM.
    """

    model_schema_version: int
    agent_logic_version: str
    modeling_prompt_version: str
    explanation_prompt_version: str
    build_attempts: int
    max_rebuilds: int
    explanation_attempts: int
    llm_model: str
    llm_provider: str
    llm_structured_mode: str
    llm_temperature: float
    llm_reasoning_effort: str
    llm_reasoning_mode: str
    llm_max_attempts: int

    def as_dict(self) -> dict[str, Any]:
        """Представление профиля без секретов — для ключа и сохранения."""
        return {
            "model_schema_version": self.model_schema_version,
            "agent_logic_version": self.agent_logic_version,
            "modeling_prompt_version": self.modeling_prompt_version,
            "explanation_prompt_version": self.explanation_prompt_version,
            "build_attempts": self.build_attempts,
            "max_rebuilds": self.max_rebuilds,
            "explanation_attempts": self.explanation_attempts,
            "llm_model": self.llm_model,
            "llm_provider": self.llm_provider,
            "llm_structured_mode": self.llm_structured_mode,
            "llm_temperature": self.llm_temperature,
            "llm_reasoning_effort": self.llm_reasoning_effort,
            "llm_reasoning_mode": self.llm_reasoning_mode,
            "llm_max_attempts": self.llm_max_attempts,
        }

    def fingerprint(self) -> str:
        """Отпечаток профиля: SHA-256 канонического JSON.

        Канонизация (сортировка ключей, UTF-8, компактные разделители)
        совпадает с правилами ключа входа из контракта §3.1: одинаковый профиль
        даёт одинаковый отпечаток, любое значимое изменение — новый.
        """
        canonical = json.dumps(
            self.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def generation_profile(
    settings: LLMSettings,
    *,
    build_attempts: int,
    max_rebuilds: int,
    explanation_attempts: int,
    reasoning: bool | None,
) -> GenerationProfile:
    """Собрать профиль прогона из настроек провайдера и границ итерации.

    Args:
        settings: Настройки LLM из окружения.
        build_attempts: Бюджет попыток построения модели.
        max_rebuilds: Лимит перестроений.
        explanation_attempts: Бюджет попыток объяснения.
        reasoning: Выбранный режим рассуждений; ``None`` — умолчание провайдера.

    Returns:
        Профиль для сохранения и ключа повторного использования.
    """
    if reasoning is None:
        reasoning_mode = "provider_default"
    elif reasoning:
        reasoning_mode = f"enabled:{settings.reasoning_effort}"
    else:
        reasoning_mode = "disabled"
    return GenerationProfile(
        model_schema_version=SCHEMA_VERSION,
        agent_logic_version=AGENT_LOGIC_VERSION,
        modeling_prompt_version=MODELING_PROMPT_VERSION,
        explanation_prompt_version=EXPLANATION_PROMPT_VERSION,
        build_attempts=build_attempts,
        max_rebuilds=max_rebuilds,
        explanation_attempts=explanation_attempts,
        llm_model=settings.model,
        llm_provider=settings.base_url,
        llm_structured_mode=settings.structured_mode,
        llm_temperature=0.0,
        llm_reasoning_effort=settings.reasoning_effort,
        llm_reasoning_mode=reasoning_mode,
        llm_max_attempts=settings.max_attempts,
    )
