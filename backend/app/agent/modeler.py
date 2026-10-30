"""Построение ``BehavioralModel`` из текста требования.

Агент отвечает за смысл, домен — за форму: ответ модели проверяется моделью
ответа (:mod:`app.agent.schema_models`), которая строит ``BehavioralModel`` до
того, как документ попадёт в базу или в движок. Невалидный документ не
сохраняется: Instructor переспрашивает модель, а исчерпание попыток становится
``LLMResponseError`` с перечнем нарушений.
"""

from collections.abc import Sequence

from app.agent.llm import LLMClient
from app.agent.prompts import MODELING_PROMPT_VERSION, MODELING_SYSTEM, modeling_user
from app.agent.schema_models import WireModelDocument
from app.domain.behavioral_model import BehavioralModel


async def build_model(
    client: LLMClient,
    *,
    requirement_text: str,
    attempts: int,
    feedback: Sequence[str] = (),
    reasoning: bool | None = None,
) -> BehavioralModel:
    """Превратить текст требования в проверяемую модель.

    Args:
        client: Клиент LLM.
        requirement_text: Исходное описание модуля.
        attempts: Сколько попыток дать модели на исправление документа.
        feedback: Замечания к прошлой модели, если модель строится заново.
        reasoning: Рассуждать ли модели до ответа; ``None`` — поведение
            провайдера по умолчанию.

    Returns:
        Валидная модель; её домены конечны и все ссылки разрешены.

    Raises:
        LLMResponseError: за отведённые попытки валидная модель не получилась.
        LLMError: провайдер недоступен или отказал в запросе.
    """
    document = await client.parse(
        WireModelDocument,
        system=MODELING_SYSTEM,
        user=modeling_user(requirement_text, feedback),
        prompt_version=MODELING_PROMPT_VERSION,
        attempts=attempts,
        reasoning=reasoning,
    )
    return document.to_domain()
