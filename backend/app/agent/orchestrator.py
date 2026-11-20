"""Цикл агента: от текста требования к результату проверки.

Итерация описана явным ациклическим графом в :mod:`app.agent.graph`:

1. ``build_0`` — модель строится по тексту требования.
2. ``gate_0`` — ворота проверяют, что каждое правило подкреплено цитатой. Не
   прошла — управление уходит в ``build_1`` со списком замечаний; таких пар
   ровно столько, сколько разрешено лимитом перестроений.
3. ``check`` — свойства проверяет детерминированный движок.
4. ``explain`` — нарушение разбирается на языке требований.
5. ``finish`` / ``fail`` — честный итог: спросить пользователя, остановиться
   или признать ``AGENT_ERROR``.

Модуль оставлен точкой входа, чтобы вызывающая сторона не зависела от того,
чем именно собран граф. Раньше здесь был императивный цикл; публичный интерфейс
не изменился.
"""

from __future__ import annotations

from app.agent.generation import GenerationProfile, generation_profile
from app.agent.graph import (
    ENGINE_WHEN_AGENT_FAILED,
    CheckProperty,
    CycleLimits,
    CycleState,
    Iteration,
    ModelHandler,
    compiled_graph,
    graph_mermaid,
    run_iteration,
)
from app.agent.stages import (
    AgentEvent,
    AgentRebuild,
    Stage,
    StageEmitter,
    StageReporter,
)

__all__ = [
    "ENGINE_WHEN_AGENT_FAILED",
    "AgentEvent",
    "AgentRebuild",
    "CheckProperty",
    "CycleLimits",
    "CycleState",
    "GenerationProfile",
    "Iteration",
    "ModelHandler",
    "Stage",
    "StageEmitter",
    "StageReporter",
    "compiled_graph",
    "generation_profile",
    "graph_mermaid",
    "run_iteration",
]
