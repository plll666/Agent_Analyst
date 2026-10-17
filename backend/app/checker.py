from typing import Protocol

from app.domain.behavioral_model import BehavioralModel
from app.domain.verification import VerificationExplanation, VerificationResult, VerificationStatus

ENGINE_STUB = "stub"
ENGINE_ERROR_DETAIL = "Проверка не выполнена: движок моделирования не подключён"
SUMMARY_ENGINE_MISSING = (
    "Проверка не запущена: к системе не подключён движок, который перебирает состояния. "
    "Результата нет — это не подтверждение корректности."
)


class Checker(Protocol):
    """Проверка модели детерминированным движком."""

    async def check(self, model: BehavioralModel, property_id: str) -> VerificationResult: ...


class StubChecker:
    """Заглушка на место реального движка."""

    engine = ENGINE_STUB
    engine_version: str | None = None

    async def check(self, model: BehavioralModel, property_id: str) -> VerificationResult:
        return VerificationResult(
            status=VerificationStatus.ENGINE_ERROR,
            property_id=property_id,
            engine=self.engine,
            engine_version=self.engine_version,
            error_detail=f"{ENGINE_ERROR_DETAIL}; переменных в модели: {len(model.variables)}",
            duration_ms=0,
        )

    @staticmethod
    def explain() -> VerificationExplanation:
        return VerificationExplanation(business_summary=SUMMARY_ENGINE_MISSING)
