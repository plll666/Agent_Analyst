"""Приёмка задачи 2: ``check_behavior`` и запись результата в ``verifications``.

Тесты, которым нужен сам TLC, помечены ``requires_java``: без jar они пропускаются,
а не падают с ``ENGINE_ERROR``. Остальные проверяют путь до движка — невалидную
модель, отсутствующий jar, тексты статусов — и работают без Java.

Тесты повторяют критерии приёмки из кейса: acceptance test 1 даёт
``PROPERTY_VIOLATED`` с контрпримером ``Created → Approve → Cancel → Execute``,
test 2 — ``PROPERTY_HOLDS``, и строка лежит в базе. Плюс проверяется то, что
запрещено архитектурой: неудача не выдаётся за успех, а объяснение не затирается
пустой строкой.
"""

import uuid
from pathlib import Path
from typing import Any

import pytest

from app.agent.llm import LLMError
from app.database.models import ModelVersion, Requirement
from app.database.session import session_scope
from app.domain.explanation import summary_for
from app.domain.verification import VerificationResult, VerificationStatus
from app.worker.main import _LLM_KEY, CheckBehaviorError, check_behavior
from app.worker.model_checker import EngineSettings, ModelChecker
from tests.agent.support import FakeLLM, explanation_payload
from tests.worker.support import (
    SeededRun,
    acceptance_model,
    fetch_artifact_kinds,
    fetch_verification,
    requires_java,
    seed_raw_document,
    seed_store_document,
)

pytestmark = [pytest.mark.integration]


@requires_java
async def test_violated_model_writes_row_with_counterexample(
    worker_ctx: dict[str, Any], seeded_run: SeededRun, sessions: Any
) -> None:
    """Acceptance test 1: нарушение найдено, путь восстановлен, строка записана."""
    await seed_store_document(sessions, seeded_run.model_version_id, acceptance_model(False))

    status = await check_behavior(worker_ctx, str(seeded_run.verification_id))

    assert status == "PROPERTY_VIOLATED"
    row = await fetch_verification(sessions, seeded_run.verification_id)
    assert row is not None
    assert row.status == "PROPERTY_VIOLATED"
    assert row.property_id == "P2"
    assert row.counterexample is not None
    steps = row.counterexample["steps"]
    # На проводе null не ходит: у шага 0 ключа transition нет, и это читается как None.
    assert [step.get("transition") for step in steps][-4:] == [None, "Approve", "Cancel", "Execute"]
    assert steps[0]["state"]["status"] == "Created"
    assert steps[-1]["state"]["status"] == "Executed"


@requires_java
async def test_fixed_model_writes_property_holds(
    worker_ctx: dict[str, Any], seeded_run: SeededRun, sessions: Any
) -> None:
    """Acceptance test 2: исправленная модель проходит, контрпримера нет."""
    await seed_store_document(sessions, seeded_run.model_version_id, acceptance_model(True))

    status = await check_behavior(worker_ctx, str(seeded_run.verification_id))

    assert status == "PROPERTY_HOLDS"
    row = await fetch_verification(sessions, seeded_run.verification_id)
    assert row is not None
    assert row.status == "PROPERTY_HOLDS"
    assert row.counterexample is None
    assert row.business_summary.strip()


@requires_java
async def test_property_holds_summary_cautions_about_scope(
    worker_ctx: dict[str, Any], seeded_run: SeededRun, sessions: Any
) -> None:
    """Успех обязан быть оговорен: проверена модель, а не система."""
    await seed_store_document(sessions, seeded_run.model_version_id, acceptance_model(True))

    await check_behavior(worker_ctx, str(seeded_run.verification_id))

    row = await fetch_verification(sessions, seeded_run.verification_id)
    assert row is not None
    assert "не доказательство" in row.business_summary


async def test_engine_failure_is_written_to_the_row_not_hidden_as_success(
    worker_ctx: dict[str, Any], seeded_run: SeededRun, sessions: Any, tmp_path: Path
) -> None:
    """Сбой движка пишется в базу с пояснением и не остаётся в PENDING."""
    await seed_store_document(sessions, seeded_run.model_version_id, acceptance_model(True))
    worker_ctx["model_checker"] = ModelChecker(
        EngineSettings(
            jar=Path("/nonexistent/tla2tools.jar"),
            timeout_seconds=5,
            state_limit=1_000,
            workers="1",
            work_dir=tmp_path,
        )
    )

    status = await check_behavior(worker_ctx, str(seeded_run.verification_id))

    row = await fetch_verification(sessions, seeded_run.verification_id)
    assert row is not None
    assert status == row.status == "ENGINE_ERROR"
    assert row.status != "PENDING"
    assert row.business_summary.strip()


async def test_invalid_document_is_reported_as_model_invalid(
    worker_ctx: dict[str, Any], seeded_run: SeededRun, sessions: Any
) -> None:
    """Документ, который домен отверг, не уходит в движок и не выдаётся за успех."""
    await seed_raw_document(sessions, seeded_run.model_version_id, {"variables": []})

    status = await check_behavior(worker_ctx, str(seeded_run.verification_id))

    row = await fetch_verification(sessions, seeded_run.verification_id)
    assert row is not None
    assert status == "MODEL_INVALID"
    assert row.status == "MODEL_INVALID"
    assert row.counterexample is None
    assert row.business_summary.strip()


@requires_java
async def test_records_artifacts_for_reproduction(
    worker_ctx: dict[str, Any], seeded_run: SeededRun, sessions: Any
) -> None:
    """Спецификация, конфигурация и вывод движка остаются для ручного прогона."""
    await seed_store_document(sessions, seeded_run.model_version_id, acceptance_model(True))

    await check_behavior(worker_ctx, str(seeded_run.verification_id))

    assert await fetch_artifact_kinds(sessions, seeded_run.verification_id) == [
        "tla_spec",
        "tlc_config",
        "tlc_output",
    ]


async def test_unknown_verification_raises_instead_of_passing_silently(
    worker_ctx: dict[str, Any],
) -> None:
    """Прогона нет — сохранять некуда, и arq должен увидеть падение."""
    with pytest.raises(CheckBehaviorError):
        await check_behavior(worker_ctx, str(uuid.uuid4()))


@pytest.mark.parametrize(
    "status",
    [
        VerificationStatus.TIMEOUT,
        VerificationStatus.STATE_LIMIT_REACHED,
        VerificationStatus.MODEL_INVALID,
        VerificationStatus.ENGINE_ERROR,
        VerificationStatus.AGENT_ERROR,
    ],
)
def test_every_non_success_status_has_a_plain_language_summary(
    status: VerificationStatus,
) -> None:
    """Каждый неуспех обязан объясняться словами, а не пустой строкой."""
    result = VerificationResult(status=status, property_id="P1", engine="TLC")

    summary = summary_for(result.status)

    assert summary.strip()
    assert "не доказательство" not in summary


def test_pending_is_not_described_as_a_finished_result() -> None:
    """``PENDING`` — это ещё идущая задача, а не вердикт."""
    summary = summary_for(VerificationStatus.PENDING)

    assert "выполняется" in summary


REQUIREMENT_TEXT = (
    "Заявка после согласования может быть исполнена. "
    "Пользователь может отменить заявку до исполнения."
)


class _BrokenLLM:
    """Провайдер, который недоступен: результат всё равно должен сохраниться."""

    async def complete_json(self, *, system: str, user: str, prompt_version: str) -> dict[str, Any]:
        del system, user, prompt_version
        raise LLMError("нет сети")

    async def aclose(self) -> None:
        return None


async def _link_requirement(sessions: Any, run: SeededRun) -> uuid.UUID:
    """Создать требование проекта и связать с ним версию модели."""
    requirement_id = uuid.uuid4()
    async with session_scope(sessions) as session:
        session.add(
            Requirement(
                id=requirement_id,
                project_id=run.project_id,
                version=1,
                raw_text=REQUIREMENT_TEXT,
                is_current=True,
            )
        )
        await session.flush()
        version = await session.get(ModelVersion, run.model_version_id)
        assert version is not None
        version.requirement_id = requirement_id
    return requirement_id


@requires_java
async def test_violation_is_explained_in_requirement_language(
    worker_ctx: dict[str, Any], seeded_run: SeededRun, sessions: Any
) -> None:
    """Объяснение агента пишется в ту же строку, что и контрпример движка."""
    await seed_store_document(sessions, seeded_run.model_version_id, acceptance_model(False))
    await _link_requirement(sessions, seeded_run)
    worker_ctx[_LLM_KEY] = FakeLLM(explanation_payload())

    status = await check_behavior(worker_ctx, str(seeded_run.verification_id))

    row = await fetch_verification(sessions, seeded_run.verification_id)
    assert row is not None
    assert status == row.status == "PROPERTY_VIOLATED"
    assert row.hypothesis == "В модели нет условия, запрещающего исполнение отменённой заявки."
    assert row.question == "Должна ли отменённая заявка оставаться исполнимой?"
    assert row.root_cause == "REQUIREMENT_ERROR"
    assert row.business_summary.splitlines() == [f"Шаг {index}." for index in range(1, 5)]
    assert row.related_requirements == [
        {"quote": "Пользователь может отменить заявку до исполнения."}
    ]


@requires_java
async def test_unavailable_llm_keeps_counterexample_with_honest_fallback(
    worker_ctx: dict[str, Any], seeded_run: SeededRun, sessions: Any
) -> None:
    """Отказ провайдера не отменяет проверку и не выдаёт шаблон за объяснение."""
    await seed_store_document(sessions, seeded_run.model_version_id, acceptance_model(False))
    worker_ctx[_LLM_KEY] = _BrokenLLM()

    status = await check_behavior(worker_ctx, str(seeded_run.verification_id))

    row = await fetch_verification(sessions, seeded_run.verification_id)
    assert row is not None
    assert status == row.status == "PROPERTY_VIOLATED"
    assert row.counterexample is not None
    assert "Найден контрпример" in row.business_summary
    assert row.hypothesis is None
    assert row.question is None
    assert row.root_cause is None


@requires_java
async def test_success_is_not_sent_to_llm(
    worker_ctx: dict[str, Any], seeded_run: SeededRun, sessions: Any
) -> None:
    """``PROPERTY_HOLDS`` — отсутствие нарушений в модели, а не сценарий для модели."""
    await seed_store_document(sessions, seeded_run.model_version_id, acceptance_model(True))
    worker_ctx[_LLM_KEY] = FakeLLM()

    status = await check_behavior(worker_ctx, str(seeded_run.verification_id))

    row = await fetch_verification(sessions, seeded_run.verification_id)
    assert row is not None
    assert status == row.status == "PROPERTY_HOLDS"
    assert "не доказательство" in row.business_summary
    assert row.root_cause is None
