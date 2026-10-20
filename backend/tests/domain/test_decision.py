"""Правило «Stop / Ask Rule»: спросить пользователя или остановиться."""

import pytest

from app.domain.decision import AnalysisDecision, decide
from app.domain.verification import VerificationStatus


@pytest.mark.parametrize(
    "status",
    [
        VerificationStatus.PROPERTY_HOLDS,
        VerificationStatus.MODEL_INVALID,
        VerificationStatus.TIMEOUT,
        VerificationStatus.STATE_LIMIT_REACHED,
        VerificationStatus.ENGINE_ERROR,
        VerificationStatus.AGENT_ERROR,
    ],
)
def test_stops_when_there_is_nothing_to_ask(status: VerificationStatus) -> None:
    """Уточнять нечего — цикл заканчивается с честным результатом."""
    assert decide(status) is AnalysisDecision.STOP


def test_asks_after_violation() -> None:
    """При нарушении у пользователя есть что уточнить."""
    assert decide(VerificationStatus.PROPERTY_VIOLATED) is AnalysisDecision.ASK


def test_pending_run_has_no_decision_yet() -> None:
    """Идущий прогон не решён: решение принимается по терминальному статусу."""
    with pytest.raises(ValueError, match="терминальному статусу"):
        decide(VerificationStatus.PENDING)
