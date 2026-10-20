"""Построение ``BehavioralModel`` из текста требования.

Агент отвечает за смысл, домен — за форму: ответ модели проходит
``BehavioralModel.model_validate`` до того, как попадёт в базу или в движок.
Невалидный документ не сохраняется, а возвращается вызывающей стороне как ошибка
с перечнем нарушений.
"""

from collections.abc import Mapping
from typing import Any

from app.agent.llm import LLMClient, request_validated
from app.agent.prompts import MODELING_PROMPT_VERSION, MODELING_SYSTEM, modeling_user
from app.domain.behavioral_model import BehavioralModel


async def build_model(
    client: LLMClient, *, requirement_text: str, attempts: int
) -> BehavioralModel:
    """Превратить текст требования в проверяемую модель.

    Args:
        client: Клиент LLM.
        requirement_text: Исходное описание модуля.
        attempts: Сколько попыток дать модели на исправление документа.

    Returns:
        Валидная модель; её домены конечны и все ссылки разрешены.

    Raises:
        LLMResponseError: за отведённые попытки валидная модель не получилась.
        LLMError: провайдер недоступен или вернул не JSON.
    """
    return await request_validated(
        client,
        system=MODELING_SYSTEM,
        user=modeling_user(requirement_text),
        prompt_version=MODELING_PROMPT_VERSION,
        attempts=attempts,
        parse=_parse_model,
    )


def _parse_model(payload: Mapping[str, Any]) -> BehavioralModel:
    """Достать документ из ответа и проверить его доменом.

    Обёртки ``{"document": ...}`` и ``{"model": ...}`` принимаются, потому что
    модели иногда добавляют их вопреки инструкции; всё остальное отвергает сам
    ``BehavioralModel`` (``extra="forbid"``).
    """
    document: Mapping[str, Any] = payload
    for key in ("document", "model"):
        nested = payload.get(key)
        if isinstance(nested, Mapping):
            document = nested
            break
    return BehavioralModel.model_validate(document)
