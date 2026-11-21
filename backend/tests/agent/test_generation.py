"""Профиль генерации: что входит в профиль и как он становится отпечатком.

Задание А7 требует зафиксировать версии промптов, модель LLM и фактические
параметры генерации, включая режим рассуждений. Профиль входит в ключ
повторного использования (контракт §3.1), поэтому проверяется и состав полей,
и стабильность отпечатка: одинаковые настройки — одинаковый ключ, любое
значимое изменение — новый.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from app.agent.generation import (
    AGENT_LOGIC_VERSION,
    GenerationProfile,
    generation_profile,
)
from app.agent.graph import CycleLimits, run_iteration
from app.agent.prompts import EXPLANATION_PROMPT_VERSION, MODELING_PROMPT_VERSION
from app.domain.behavioral_model import MODEL_SCHEMA_VERSION, BehavioralModel, Property
from app.domain.verification import VerificationResult
from tests.agent.support import FakeLLM, cited_payload, explanation_payload, settings
from tests.domain.case_examples import CASE_RESULT_VIOLATED, case_model

REQUIREMENT = (
    "Заявка после согласования может быть исполнена. "
    "Пользователь может отменить заявку до исполнения."
)
QUOTE = "Заявка после согласования может быть исполнена"
SECRET = "sk-live-very-secret-value"
LIMITS = CycleLimits(build_attempts=3, max_rebuilds=2, explanation_attempts=4)


def _profile(**overrides: Any) -> GenerationProfile:
    values: dict[str, Any] = {
        "build_attempts": LIMITS.build_attempts,
        "max_rebuilds": LIMITS.max_rebuilds,
        "explanation_attempts": LIMITS.explanation_attempts,
        "reasoning": None,
    }
    values.update(overrides)
    return generation_profile(settings(), **values)


def test_profile_captures_versions_model_and_limits() -> None:
    profile = _profile()

    assert profile.model_schema_version == MODEL_SCHEMA_VERSION
    assert profile.agent_logic_version == AGENT_LOGIC_VERSION
    assert profile.modeling_prompt_version == MODELING_PROMPT_VERSION
    assert profile.explanation_prompt_version == EXPLANATION_PROMPT_VERSION
    assert (profile.build_attempts, profile.max_rebuilds, profile.explanation_attempts) == (3, 2, 4)
    assert profile.llm_model == "test-model"
    assert profile.llm_provider == "https://llm.example/v1"
    assert profile.llm_temperature == 0.0
    assert profile.llm_max_attempts == 3


def test_reasoning_mode_describes_the_actual_request() -> None:
    """Режим рассуждений записывается так, как он уйдёт провайдеру."""
    assert _profile(reasoning=None).llm_reasoning_mode == "provider_default"
    assert _profile(reasoning=False).llm_reasoning_mode == "disabled"
    enabled = _profile(reasoning=True)
    assert enabled.llm_reasoning_mode == "enabled:high"
    assert enabled.llm_reasoning_effort == "high"


def test_reasoning_effort_comes_from_provider_settings() -> None:
    profile = generation_profile(
        settings(reasoning_effort="medium"),
        build_attempts=1,
        max_rebuilds=0,
        explanation_attempts=1,
        reasoning=True,
    )

    assert profile.llm_reasoning_mode == "enabled:medium"


def test_profile_does_not_leak_the_api_key() -> None:
    """Ключ провайдера не попадает ни в поля профиля, ни в отпечаток."""
    profile = generation_profile(
        settings(api_key=SECRET),
        build_attempts=1,
        max_rebuilds=0,
        explanation_attempts=1,
        reasoning=None,
    )
    serialized = repr(profile.as_dict()) + profile.fingerprint()

    assert SECRET not in serialized
    assert "api_key" not in profile.as_dict()


def test_fingerprint_is_stable_for_the_same_profile() -> None:
    first = _profile()
    second = _profile()

    assert first.fingerprint() == second.fingerprint()
    assert first.fingerprint() == first.fingerprint()
    assert len(first.fingerprint()) == 64
    assert set(first.fingerprint()) <= set("0123456789abcdef")


@pytest.mark.parametrize(
    "overrides",
    [
        {"reasoning": False},
        {"max_rebuilds": 1},
        {"build_attempts": 2},
        {"explanation_attempts": 1},
    ],
)
def test_fingerprint_changes_with_generation_settings(overrides: dict[str, Any]) -> None:
    assert _profile().fingerprint() != _profile(**overrides).fingerprint()


def test_fingerprint_changes_with_the_model() -> None:
    other = generation_profile(
        settings(model="other-model"),
        build_attempts=LIMITS.build_attempts,
        max_rebuilds=LIMITS.max_rebuilds,
        explanation_attempts=LIMITS.explanation_attempts,
        reasoning=None,
    )

    assert _profile().fingerprint() != other.fingerprint()


def test_fingerprint_changes_with_the_provider_address() -> None:
    """Адрес шлюза влияет на результат, значит, входит в ключ."""
    other = generation_profile(
        settings(base_url="https://other.example/v1"),
        build_attempts=LIMITS.build_attempts,
        max_rebuilds=LIMITS.max_rebuilds,
        explanation_attempts=LIMITS.explanation_attempts,
        reasoning=None,
    )

    assert _profile().fingerprint() != other.fingerprint()


def test_profile_is_immutable() -> None:
    profile = _profile()

    with pytest.raises(FrozenInstanceError):
        profile.llm_model = "changed"  # type: ignore[misc]


async def _violated(model: BehavioralModel, prop: Property) -> VerificationResult:
    _ = (model, prop)
    return VerificationResult.model_validate(CASE_RESULT_VIOLATED)


async def test_iteration_returns_the_generation_profile_as_is() -> None:
    profile = _profile()
    client = FakeLLM(cited_payload(case_model(), QUOTE), explanation_payload())

    iteration = await run_iteration(
        client=client,
        requirement_text=REQUIREMENT,
        check_property=_violated,
        limits=LIMITS,
        generation=profile,
    )

    assert iteration.generation == profile
    assert iteration.generation is profile


async def test_iteration_without_profile_has_nothing_to_compare() -> None:
    client = FakeLLM(cited_payload(case_model(), QUOTE), explanation_payload())

    iteration = await run_iteration(
        client=client,
        requirement_text=REQUIREMENT,
        check_property=_violated,
        limits=LIMITS,
    )

    assert iteration.generation is None
