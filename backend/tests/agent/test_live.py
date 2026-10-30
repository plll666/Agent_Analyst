"""Сквозная приёмка: текст требования → модель агента → TLC → объяснение → ответ.

Тест ходит в настоящую LLM и пропускается, если провайдер не настроен: без ключа
он не должен притворяться зелёным. Проверяется кейс целиком, а не форма ответа:

1. по исходному тексту агент строит модель, в которой отменённая заявка всё ещё
   исполнима, объясняет именно эту трассу и задаёт вопрос пользователю;
2. ответ пользователя становится уточнением требования, и по уточнённому тексту
   цикл сходится: именно ``PROPERTY_HOLDS`` (не ``AGENT_ERROR`` и не ``TIMEOUT``),
   никакого нового вопроса — агент остановился сам.
"""

from pathlib import Path

import pytest

from app.agent.llm import LLMClient, LLMSettings, client_from_env
from app.agent.orchestrator import Iteration, run_iteration
from app.domain.behavioral_model import BehavioralModel, Property
from app.domain.verification import VerificationResult, VerificationStatus
from app.worker.model_checker import EngineSettings, ModelChecker
from tests.worker.support import JAR, requires_java

CASE_TEXT = (
    "Заявка после согласования может быть исполнена. "
    "Пользователь может отменить заявку до исполнения."
)
ANSWER_TEXT = "Отменённая заявка исполняться не должна."

SETTINGS = LLMSettings.from_env()

pytestmark = [pytest.mark.agent, pytest.mark.integration]


async def _iterate(client: LLMClient, checker: ModelChecker, requirement_text: str) -> Iteration:
    """Провести итерацию цикла с настоящим движком TLC."""

    async def check_property(model: BehavioralModel, prop: Property) -> VerificationResult:
        outcome = await checker.check(model, prop)
        return outcome.result

    return await run_iteration(
        client=client,
        requirement_text=requirement_text,
        check_property=check_property,
    )


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
        checker = ModelChecker(
            EngineSettings(
                jar=JAR,
                timeout_seconds=60,
                state_limit=1_000_000,
                workers="1",
                work_dir=tmp_path,
            )
        )

        first = await _iterate(client, checker, CASE_TEXT)

        assert first.status is VerificationStatus.PROPERTY_VIOLATED, (
            "агент построил модель без нарушения: промпт добавил правило, которого нет в тексте"
        )
        assert first.result is not None
        assert first.result.counterexample is not None
        assert first.explanation.hypothesis
        assert first.explanation.question
        assert first.explanation.root_cause is not None
        assert len(first.explanation.business_summary.splitlines()) == len(
            first.result.counterexample.steps
        )
        for requirement in first.result.related_requirements or ():
            assert requirement.quote is None or requirement.quote in CASE_TEXT

        clarified = f"{CASE_TEXT}\n\nУточнение пользователя: {ANSWER_TEXT}"
        second = await _iterate(client, checker, clarified)

        assert second.status is VerificationStatus.PROPERTY_HOLDS, (
            "цикл не сошёлся: ожидалось PROPERTY_HOLDS, получилось "
            f"{second.status.value if second.status else None}"
        )
        assert second.explanation.question is None, (
            "цикл не сошёлся: агент снова спрашивает пользователя вместо остановки"
        )
    finally:
        await client.aclose()
