"""Сборка ключа входа прогона из конфигурации запуска.

Контракт спринта 3, раздел 3.1: ключ складывается из версии алгоритма,
проекта и выбранной версии требования с хэшем текста, версии схемы модели,
версий промптов и логики агента с лимитами, идентификатора конфигурации
провайдера и модели со всеми фактическими параметрами генерации, а также
версий ядра и лимитов проверки.

Секреты (API-ключ) в ключ не входят: конфигурация провайдера попадает в
ключ только своим хэшем. Изменение любого значимого поля даёт другой ключ,
и прежний результат не переиспользуется молча.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from typing import Any

from app.agent.graph import AGENT_LOGIC_VERSION, MAX_REBUILDS
from app.agent.llm import LLMSettings
from app.agent.prompts import EXPLANATION_PROMPT_VERSION, MODELING_PROMPT_VERSION
from app.config import get_settings
from app.domain.behavioral_model import MODEL_SCHEMA_VERSION
from app.domain.input_key import (
    KEY_ALGORITHM_VERSION,
    canonical_json,
    compute_input_key,
    text_digest,
)
from app.worker.model_checker import EngineSettings

# Версии алгоритмов ядра: их меняют вместе с ``app.domain.tla`` и
# ``app.domain.tlc_output`` — другой разбор вывода даёт другие статусы.
TLA_COMPILER_VERSION = "tla-compiler-1"
TLC_PARSER_VERSION = "tlc-output-1"

# Фактические параметры генерации: temperature зашит в клиенте LLM
# (``app.agent.llm``) и одинаков для всех вызовов, поэтому входит в ключ
# константой, а не читается из окружения.
GENERATION_SETTINGS: dict[str, Any] = {"temperature": 0}


def analysis_config_snapshot(reasoning: bool | None) -> dict[str, Any]:
    """Параметры генерации и проверки, сохранённые вместе с прогоном."""
    llm = LLMSettings.from_env()
    engine = EngineSettings.from_env()
    return {
        "prompts": {
            "modeling": MODELING_PROMPT_VERSION,
            "explanation": EXPLANATION_PROMPT_VERSION,
        },
        "agent_logic": AGENT_LOGIC_VERSION,
        "model_schema": MODEL_SCHEMA_VERSION,
        "llm_max_input_chars": get_settings().llm_max_input_chars,
        "llm": {
            "model": llm.model,
            "config_id": llm_config_id(llm),
            "reasoning": reasoning,
            "reasoning_effort": llm.reasoning_effort
            if reasoning
            else "none"
            if reasoning is False
            else None,
            "structured_mode": llm.structured_mode,
            **GENERATION_SETTINGS,
        },
        "engine": _engine_part(engine),
    }


def model_check_config_snapshot() -> dict[str, Any]:
    """Настройки детерминированного ядра отдельной проверки модели."""
    return {"model_schema": MODEL_SCHEMA_VERSION, "engine": _engine_part(EngineSettings.from_env())}


def llm_config_id(settings: LLMSettings) -> str:
    """Идентификатор конфигурации провайдера без секретов.

    Хэш складывается из адреса, модели, режима структурного ответа и усилия
    рассуждения: смена модели по изменяемому алиасу или смена умолчаний
    провайдера меняет идентификатор, и прежний результат не переиспользуется.

    Args:
        settings: Настройки клиента LLM.

    Returns:
        Строка ``sha256:<hex>``.
    """
    digest = hashlib.sha256(
        canonical_json(
            {
                "base_url": settings.base_url,
                "model": settings.model,
                "structured_mode": settings.structured_mode,
                "reasoning_effort": settings.reasoning_effort,
                "reasoning_supported": settings.reasoning_supported,
                "timeout_seconds": settings.timeout_seconds,
                "transport_retries": settings.transport_retries,
                "transport_backoff_seconds": settings.transport_backoff_seconds,
                "configuration_version": os.getenv("LLM_CONFIGURATION_VERSION", "1"),
            }
        )
    ).hexdigest()
    return f"sha256:{digest}"


def analysis_input_key(
    *,
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    requirement_text: str,
    reasoning: bool | None,
) -> str:
    """Ключ входа итерации агента.

    Args:
        project_id: Проект, в котором запускается анализ.
        requirement_id: Зафиксированная версия требования: новая версия —
            новый вход, даже при совпадающем тексте.
        requirement_text: Точный сохранённый текст требования.
        reasoning: Режим рассуждений запроса; ``None`` — умолчание провайдера.

    Returns:
        Строка ``sha256:<hex>``.
    """
    llm = LLMSettings.from_env()
    engine = EngineSettings.from_env()
    return compute_input_key(
        {
            "algorithm": KEY_ALGORITHM_VERSION,
            "project_id": str(project_id),
            "requirement": {
                "id": str(requirement_id),
                "text_sha256": text_digest(requirement_text),
            },
            "model_schema": MODEL_SCHEMA_VERSION,
            "prompts": {
                "modeling": MODELING_PROMPT_VERSION,
                "explanation": EXPLANATION_PROMPT_VERSION,
            },
            "agent": {
                "logic": AGENT_LOGIC_VERSION,
                "max_rebuilds": MAX_REBUILDS,
                "build_attempts": llm.max_attempts,
                "explanation_attempts": llm.max_attempts,
            },
            "llm": {
                "config_id": llm_config_id(llm),
                "model": llm.model,
                "generation": {
                    **GENERATION_SETTINGS,
                    "structured_mode": llm.structured_mode,
                    "reasoning_effort": llm.reasoning_effort,
                },
                "reasoning": reasoning,
                "max_input_chars": get_settings().llm_max_input_chars,
            },
            "engine": _engine_part(engine),
        }
    )


def model_check_input_key(*, project_id: uuid.UUID, model_version_id: uuid.UUID) -> str:
    """Ключ входа прогона, проверяющего уже построенную модель.

    Отдельная ветка API (``POST /verifications``) не переиспользует результаты
    по ключу, но поле ``input_key`` обязано быть заполнено и у неё: вход такого
    прогона — конкретная версия модели и конфигурация ядра.

    Args:
        project_id: Проект.
        model_version_id: Версия модели, которую проверяют.

    Returns:
        Строка ``sha256:<hex>``.
    """
    engine = EngineSettings.from_env()
    return compute_input_key(
        {
            "algorithm": KEY_ALGORITHM_VERSION,
            "kind": "model_check",
            "project_id": str(project_id),
            "model_version_id": str(model_version_id),
            "model_schema": MODEL_SCHEMA_VERSION,
            "engine": _engine_part(engine),
        }
    )


def _engine_part(engine: EngineSettings) -> dict[str, Any]:
    """Версии и лимиты проверки — общая часть обоих ключей."""
    return {
        "compiler": TLA_COMPILER_VERSION,
        "parser": TLC_PARSER_VERSION,
        "version": engine.version,
        "timeout_seconds": engine.timeout_seconds,
        "state_limit": engine.state_limit,
        "workers": engine.workers,
    }
