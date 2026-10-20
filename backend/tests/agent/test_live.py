"""Сквозная приёмка: текст требования → модель агента → TLC → объяснение.

Тест ходит в настоящую LLM и пропускается, если провайдер не настроен: без ключа
он не должен притворяться зелёным. Проверяется не форма ответа, а кейс целиком:
агент обязан построить модель, в которой отменённая заявка всё ещё исполнима, а
объяснение — описать именно эту трассу и задать вопрос пользователю.
"""

from pathlib import Path

import pytest

from app.agent.explainer import explain_result
from app.agent.llm import LLMSettings, client_from_env
from app.agent.modeler import build_model
from app.domain.verdict import combine
from app.domain.verification import VerificationStatus
from app.worker.model_checker import EngineSettings, ModelChecker
from tests.worker.support import JAR, requires_java

CASE_TEXT = (
    "Заявка после согласования может быть исполнена. "
    "Пользователь может отменить заявку до исполнения."
)

SETTINGS = LLMSettings.from_env()

pytestmark = [pytest.mark.agent, pytest.mark.integration]


@requires_java
@pytest.mark.skipif(
    not SETTINGS.is_configured,
    reason="LLM не настроена: задайте LLM_API_KEY, LLM_BASE_URL и LLM_MODEL",
)
async def test_case_text_reproduces_the_hole_and_gets_an_explanation(
    tmp_path: Path,
) -> None:
    """Кейс из задания проходит весь цикл без ручной правки модели."""
    client = client_from_env()
    try:
        model = await build_model(
            client, requirement_text=CASE_TEXT, attempts=SETTINGS.max_attempts
        )
        checker = ModelChecker(
            EngineSettings(
                jar=JAR,
                timeout_seconds=60,
                state_limit=1_000_000,
                workers="1",
                work_dir=tmp_path,
            )
        )
        outcomes = [await checker.check(model, prop) for prop in model.properties]
        result = combine([outcome.result for outcome in outcomes])

        assert result.status is VerificationStatus.PROPERTY_VIOLATED, (
            "агент построил модель без нарушения: промпт добавил правило, которого нет в тексте"
        )
        assert result.counterexample is not None

        answered = await explain_result(
            client,
            requirement_text=CASE_TEXT,
            model=model,
            result=result,
            attempts=SETTINGS.max_attempts,
        )

        assert answered.explanation.hypothesis
        assert answered.explanation.question
        assert answered.explanation.root_cause is not None
        assert len(answered.explanation.business_summary.splitlines()) == len(
            result.counterexample.steps
        )
        for requirement in answered.related_requirements:
            assert requirement.quote is None or requirement.quote in CASE_TEXT
    finally:
        await client.aclose()
