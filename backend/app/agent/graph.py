"""Итерация агента как явный ациклический граф (DAG).

Цикл собран на LangGraph: узлы — шаги, рёбра — переходы, состояние — один
словарь. Это не дань моде: граф делает процесс проверяемым. Видно, какие шаги
существуют, что за чем идёт и где цикл заканчивается; тест обходит рёбра и
доказывает, что назад путей нет.

Почему перестройка модели развёрнута в цепочку, а не оставлена циклом:

* задание требует DAG, а ребро «ворота → построить заново» — это цикл;
* перестройка всё равно ограничена ``max_rebuilds``, поэтому граф строится под
  конкретный лимит: ``build_0 → gate_0 → check_0 → explain_0 → build_1 → ...``;
* число узлов растёт вместе с лимитом, но лимит — константа конфигурации, а не
  пользовательский ввод, так что граф остаётся небольшим и предсказуемым.

Перестройка бывает двух видов, и оба ведут только вперёд:

* ворота не пропустили модель — замечания ворот уходят в следующую сборку;
* движок нашёл нарушение, а объяснение признало ошибку самой модели
  (``AGENT_ERROR``) — объяснение уходит в следующую сборку как обратная связь.
  Спрашивать пользователя о таком нарушении бессмысленно: сначала агент должен
  исправить свою интерпретацию. Если перестроить уже некуда или объяснение
  повторяет те же замечания, прогон останавливается без вопроса.

Модуль ничего не знает про БД и очередь: на входе текст требования, клиент LLM
и способ проверить одно свойство; на выходе — результат, объяснение и решение.
Запись в базу делает вызывающая сторона. Ход выполнения агент сообщает через
необязательный callback ``emit_stage``: полный снимок этапа
(:class:`~app.domain.stages.Stage`) и факт перестроения модели. Форма события —
общая с ядром (контракт §5.1), поэтому воркер и адаптер движка рисуют один и
тот же этап одинаково.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache, partial
from typing import Any, Protocol, TypedDict, cast

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from app.agent import self_check
from app.agent.explainer import explain_result
from app.agent.generation import GenerationProfile
from app.agent.llm import LLMClient, LLMError, LLMResponseError
from app.agent.modeler import build_model
from app.agent.stages import (
    REASON_CHECK_FAILED,
    REASON_GATE_REJECTED,
    REASON_INVALID_RESPONSE,
    REASON_LLM_UNAVAILABLE,
    REASON_MODEL_INTERPRETATION_ERROR,
    StageEmitter,
    StageReporter,
)
from app.domain.behavioral_model import BehavioralModel, Property
from app.domain.decision import AnalysisDecision, decide
from app.domain.explanation import summary_for
from app.domain.stages import Stage, StageState
from app.domain.verdict import combine
from app.domain.verification import (
    RootCause,
    VerificationExplanation,
    VerificationResult,
    VerificationStatus,
)

logger = logging.getLogger(__name__)


class CheckProperty(Protocol):
    """Как проверить одно свойство модели детерминированным движком.

    Адаптер ядра сам сообщает о своих этапах (``validate``, ``tlc_run`` и
    остальные) через тот же ``emit_stage``, что получил воркер: граф не
    передаёт callback в проверку, а воркер вкладывает этапы ядра в текущий
    ``agent/check``. Так ядро не знает про DAG, а граф — про этапы движка.
    """

    async def __call__(self, model: BehavioralModel, prop: Property) -> VerificationResult:
        """Проверить одно свойство и вернуть результат."""
        ...


ModelHandler = Callable[[BehavioralModel], Awaitable[None]]

_STAGE_MESSAGE_LIMIT = 240

ENGINE_WHEN_AGENT_FAILED = "AGENT"

# Лимит перестроений по умолчанию и версия логики DAG: обе константы входят в
# ключ входа прогона (контракт спринта 3, раздел 3.1) — меняются только вместе
# с поведением графа.
MAX_REBUILDS = 2
AGENT_LOGIC_VERSION = "agent-dag-1"

# Ключи маршрутов: их возвращают узлы, по ним идут условные рёбра.
ROUTE_TO_GATE = "gate"
ROUTE_TO_CHECK = "check"
ROUTE_TO_REBUILD = "rebuild"
ROUTE_TO_FINISH = "finish"
ROUTE_TO_FAIL = "fail"


@dataclass(frozen=True, slots=True)
class CycleLimits:
    """Границы одной итерации.

    Attributes:
        build_attempts: Сколько попыток у модели на валидный документ.
        max_rebuilds: Сколько раз агент перестраивает модель после замечаний
            ворот или объяснения контрпримера.
        explanation_attempts: Сколько попыток у модели на объяснение нарушения.
    """

    build_attempts: int = 3
    max_rebuilds: int = MAX_REBUILDS
    explanation_attempts: int = 3


@dataclass(frozen=True, slots=True)
class Iteration:
    """Итог одной итерации агента.

    Attributes:
        status: Статус итерации.
        model: Построенная модель; ``None``, если агент не смог её построить.
        result: Результат проверки; ``None``, если до движка дело не дошло.
        explanation: Объяснение на языке требований.
        decision: Спросить пользователя или остановиться.
        gate_problems: Замечания ворот или объяснения, из-за которых модель
            перестраивалась.
        rebuilds: Сколько раз модель перестраивалась.
        generation: Профиль генерации прогона, если он передан вызывающей стороной.
    """

    status: VerificationStatus
    model: BehavioralModel | None
    result: VerificationResult | None
    explanation: VerificationExplanation
    decision: AnalysisDecision
    gate_problems: tuple[str, ...] = ()
    rebuilds: int = 0
    generation: GenerationProfile | None = None


class CycleState(TypedDict, total=False):
    """Состояние одного прогона графа.

    Входные ключи (``client``, ``requirement_text`` и остальные) кладёт
    вызывающая сторона, остальные заполняют узлы. ``total=False`` — потому что
    на старте половины ключей ещё нет, и это нормальный ход выполнения, а не
    недозаполненное состояние.
    """

    # Вход
    client: LLMClient
    requirement_text: str
    check_property: CheckProperty
    limits: CycleLimits
    on_model: ModelHandler | None
    reasoning: bool | None
    emit_stage: StageEmitter | None
    generation: GenerationProfile | None

    # Ход выполнения
    model: BehavioralModel | None
    problems: list[str]
    rebuilds: int
    route: str

    # Результат
    result: VerificationResult
    explanation: VerificationExplanation
    final: Iteration


async def run_iteration(
    *,
    client: LLMClient,
    requirement_text: str,
    check_property: CheckProperty,
    limits: CycleLimits | None = None,
    on_model: ModelHandler | None = None,
    reasoning: bool | None = None,
    emit_stage: StageEmitter | None = None,
    generation: GenerationProfile | None = None,
) -> Iteration:
    """Провести одну итерацию агента по графу.

    Args:
        client: Клиент LLM.
        requirement_text: Текст требования.
        check_property: Как проверить одно свойство движком.
        limits: Границы итерации; от ``max_rebuilds`` зависит форма графа.
        on_model: Что сделать с моделью, прошедшей ворота: её сохраняют и
            показывают пользователю, пока идёт проверка.
        reasoning: Рассуждать ли модели до ответа; ``None`` — поведение
            провайдера по умолчанию.
        emit_stage: Куда сообщать события этапов и перестроений; ``None`` —
            прогон без наблюдаемости.
        generation: Профиль генерации прогона; возвращается в итоге как есть.

    Returns:
        Итог итерации.
    """
    bounds = limits or CycleLimits()
    state: CycleState = {
        "client": client,
        "requirement_text": requirement_text,
        "check_property": check_property,
        "limits": bounds,
        "on_model": on_model,
        "reasoning": reasoning,
        "emit_stage": emit_stage,
        "generation": generation,
        "problems": [],
        "rebuilds": 0,
    }
    finished = cast(CycleState, await _compiled(bounds.max_rebuilds).ainvoke(state))
    return finished["final"]


def compiled_graph(max_rebuilds: int = 2) -> Any:
    """Скомпилированный граф: нужен тестам и документации.

    Args:
        max_rebuilds: Лимит перестроений, под который разворачивается цепочка.

    Returns:
        Объект LangGraph с методами ``ainvoke`` и ``get_graph``.
    """
    return _compiled(max_rebuilds)


def graph_mermaid(max_rebuilds: int = 2) -> str:
    """Mermaid-схема графа для документации: узлы и все рёбра."""
    return cast(str, _compiled(max_rebuilds).get_graph().draw_mermaid())


@lru_cache(maxsize=8)
def _compiled(max_rebuilds: int) -> Any:
    """Собрать и скомпилировать граф под лимит перестроений.

    Компиляция детерминирована и зависит только от ``max_rebuilds``, поэтому
    результат кешируется: форма графа не меняется от прогона к прогону.
    """
    if max_rebuilds < 0:
        raise ValueError("max_rebuilds не может быть отрицательным")

    builder = StateGraph(CycleState)
    last = max_rebuilds

    for attempt in range(max_rebuilds + 1):
        builder.add_node(f"build_{attempt}", partial(_build, build_index=attempt))
        builder.add_node(f"gate_{attempt}", partial(_gate, attempt=attempt))
        builder.add_node(f"check_{attempt}", partial(_check, attempt=attempt))
        builder.add_node(f"explain_{attempt}", partial(_explain_node, attempt=attempt))

        builder.add_conditional_edges(
            f"build_{attempt}",
            _route,
            {ROUTE_TO_GATE: f"gate_{attempt}", ROUTE_TO_FAIL: "fail"},
        )
        builder.add_conditional_edges(
            f"gate_{attempt}",
            _route,
            {
                ROUTE_TO_CHECK: f"check_{attempt}",
                ROUTE_TO_REBUILD: f"build_{attempt + 1}" if attempt < last else "fail",
                ROUTE_TO_FAIL: "fail",
            },
        )
        builder.add_edge(f"check_{attempt}", f"explain_{attempt}")
        builder.add_conditional_edges(
            f"explain_{attempt}",
            _route,
            {
                ROUTE_TO_FINISH: "finish",
                ROUTE_TO_REBUILD: f"build_{attempt + 1}" if attempt < last else "finish",
            },
        )

    builder.add_node("finish", _finish)
    builder.add_node("fail", _fail)

    builder.add_edge(START, "build_0")
    builder.add_edge("finish", END)
    builder.add_edge("fail", END)

    return builder.compile()


async def _observe(state: CycleState, *, name: str, attempt: int, handler: Any) -> dict[str, Any]:
    emit = state.get("emit_stage")
    if emit is None:
        return await handler(state)
    started = datetime.now(UTC)
    stage = Stage(
        stage_id=str(uuid.uuid4()),
        scope="agent",
        name=name,
        state=StageState.RUNNING,
        build_index=attempt,
        attempt=1,
        started_at=started,
    )
    await emit(stage)
    try:
        result = await handler(state)
    except BaseException as error:
        finished = datetime.now(UTC)
        await emit(
            stage.model_copy(
                update={
                    "state": StageState.CANCELLED
                    if isinstance(error, asyncio.CancelledError)
                    else StageState.FAILED,
                    "finished_at": finished,
                    "duration_ms": max(0, int((finished - started).total_seconds() * 1000)),
                    "reason_code": "CANCEL_REQUESTED"
                    if isinstance(error, asyncio.CancelledError)
                    else "STAGE_FAILED",
                }
            )
        )
        raise
    finished = datetime.now(UTC)
    await emit(
        stage.model_copy(
            update={
                "state": StageState.SUCCEEDED,
                "finished_at": finished,
                "duration_ms": max(0, int((finished - started).total_seconds() * 1000)),
                "reason_code": ("GATE_REJECTED" if name == "gate" else "MODEL_INTERPRETATION_ERROR")
                if result.get("route") == ROUTE_TO_REBUILD
                else None,
            }
        )
    )
    return result


def _route(state: CycleState) -> str:
    """Прочитать маршрут, который выбрал предыдущий узел."""
    return state["route"]


def _reporter(state: CycleState) -> StageReporter:
    """Репортер событий этого прогона."""
    return StageReporter(state.get("emit_stage"))


def _short(text: str) -> str:
    """Обрезать длинное пояснение до размера строки статуса."""
    if len(text) <= _STAGE_MESSAGE_LIMIT:
        return text
    return text[: _STAGE_MESSAGE_LIMIT - 1].rstrip() + "…"


async def _build(state: CycleState, *, build_index: int) -> dict[str, Any]:
    """Построить модель; и первая сборка, и перестроение получают все попытки.

    Одна попытка на перестроение оказалась хрупкой: невалидный структурный
    ответ модели обрывал цикл, хотя следующая попытка обычно исправляла
    документ. Поэтому ``build_attempts`` — бюджет любого построения, а не
    только первого.
    """
    limits = state["limits"]
    problems = state.get("problems", [])
    reporter = _reporter(state)
    stage_id = await reporter.start(
        "build", build_index=build_index, message="Агент строит модель по тексту требования"
    )
    try:
        model = await build_model(
            state["client"],
            requirement_text=state["requirement_text"],
            attempts=limits.build_attempts,
            feedback=problems,
            reasoning=state.get("reasoning"),
        )
    except LLMResponseError as error:
        detail = _short("; ".join(error.problems) or str(error))
        await reporter.finish(
            stage_id,
            state="FAILED",
            reason_code=REASON_INVALID_RESPONSE,
            message=detail,
        )
        return {
            "model": None,
            "problems": [*problems, *error.problems],
            "route": ROUTE_TO_FAIL,
        }
    except (LLMError, ValidationError) as error:
        await reporter.finish(
            stage_id,
            state="FAILED",
            reason_code=REASON_LLM_UNAVAILABLE,
            message=_short(str(error)),
        )
        return {
            "model": None,
            "problems": [*problems, str(error)],
            "route": ROUTE_TO_FAIL,
        }
    await reporter.finish(stage_id, state="SUCCEEDED", message="Модель построена")
    return {"model": model, "route": ROUTE_TO_GATE}


async def _gate(state: CycleState, *, attempt: int) -> dict[str, Any]:
    """Проверить модель воротами и решить, что делать дальше."""
    model = state["model"]
    if model is None:  # защита от неверной сборки графа, а не рабочий путь
        return {"route": ROUTE_TO_FAIL}
    reporter = _reporter(state)
    stage_id = await reporter.start(
        "gate",
        build_index=attempt,
        message="Ворота проверяют, что правила модели подкреплены текстом",
    )
    gate = self_check.check(model, state["requirement_text"])
    previous = state.get("problems", [])

    if not gate:
        await reporter.finish(stage_id, state="SUCCEEDED", message="Модель прошла ворота")
        handler = state.get("on_model")
        if handler is not None:
            await handler(model)
        return {"route": ROUTE_TO_CHECK}

    message = _short(gate[0])
    await reporter.finish(
        stage_id, state="FAILED", reason_code=REASON_GATE_REJECTED, message=message
    )
    if gate == previous:
        logger.warning("ворота вернули те же замечания второй раз подряд: %s", "; ".join(gate))
        return {"problems": gate, "route": ROUTE_TO_FAIL}

    rebuilds = attempt + 1
    if attempt >= state["limits"].max_rebuilds:
        return {"problems": gate, "rebuilds": rebuilds, "route": ROUTE_TO_FAIL}
    await reporter.rebuild(
        from_build_index=attempt,
        to_build_index=attempt + 1,
        reason_code=REASON_GATE_REJECTED,
        message=message,
    )
    return {"problems": gate, "rebuilds": rebuilds, "route": ROUTE_TO_REBUILD}


async def _check(state: CycleState, *, attempt: int) -> dict[str, Any]:
    """Проверить все свойства модели детерминированным движком."""
    model = state["model"]
    if model is None:  # недостижимо: до check ведёт только пройденный gate
        raise RuntimeError("граф дошёл до проверки без модели")
    results = [
        await _check_one(state, model, prop, build_index=attempt) for prop in model.properties
    ]
    return {"result": combine(results)}


async def _check_one(
    state: CycleState, model: BehavioralModel, prop: Property, *, build_index: int
) -> VerificationResult:
    """Проверить одно свойство; этап ``check`` становится родителем этапов ядра.

    Callback в проверку не передаётся: этапы ядра приходят в воркер тем же
    ``emit_stage``, а он вкладывает их в текущий ``agent/check``. Поэтому
    ``property_id`` проверяемого свойства здесь известен, а внутри движка —
    уже нет, и связывает их воркер.
    """
    reporter = _reporter(state)
    stage_id = await reporter.start(
        "check",
        build_index=build_index,
        property_id=prop.id,
        message=f"Проверка свойства {prop.id}",
    )
    try:
        result = await state["check_property"](model, prop)
    except Exception as error:
        await reporter.finish(
            stage_id,
            state="FAILED",
            reason_code=REASON_CHECK_FAILED,
            message=_short(f"проверка свойства {prop.id} упала: {error}"),
        )
        raise
    await reporter.finish(
        stage_id,
        state="SUCCEEDED",
        message=_short(f"Свойство {prop.id}: {result.status.value}"),
        statistics=result.statistics,
    )
    return result


async def _explain_node(state: CycleState, *, attempt: int) -> dict[str, Any]:
    """Объяснить нарушение; ошибку модели — вернуть в перестройку.

    Если объяснение называет причиной саму модель, пользователю нечего уточнять:
    замечание уходит в следующую сборку. Лимит перестроений и повтор того же
    замечания останавливают цепочку — иначе агент бесконечно переписывал бы
    модель, не спрашивая человека.
    """
    model = state["model"]
    if model is None:  # недостижимо по той же причине
        raise RuntimeError("граф дошёл до объяснения без модели")
    reporter = _reporter(state)
    stage_id = await reporter.start(
        "explain",
        build_index=attempt,
        message="Агент готовит объяснение результата",
    )
    result, explanation = await _explain(
        state["client"],
        requirement_text=state["requirement_text"],
        model=model,
        result=state["result"],
        limits=state["limits"],
        reasoning=state.get("reasoning"),
    )

    if not _agent_misread(result, explanation):
        await _finish_explain_stage(reporter, stage_id, result, explanation)
        return {"result": result, "explanation": explanation, "route": ROUTE_TO_FINISH}

    feedback = _semantic_feedback(result, explanation)
    previous = state.get("problems", [])
    if feedback == previous:
        logger.warning("объяснение повторило те же замечания к модели: %s", "; ".join(feedback))
        await _finish_explain_stage(reporter, stage_id, result, explanation)
        return {
            "result": result,
            "explanation": explanation,
            "problems": feedback,
            "route": ROUTE_TO_FINISH,
        }
    if attempt >= state["limits"].max_rebuilds:
        logger.warning("объяснение признало ошибку модели, но лимит перестроений исчерпан")
        await _finish_explain_stage(reporter, stage_id, result, explanation)
        return {
            "result": result,
            "explanation": explanation,
            "problems": feedback,
            "route": ROUTE_TO_FINISH,
        }

    logger.info("объяснение признало ошибку модели, перестраиваю: %s", explanation.hypothesis)
    await _finish_explain_stage(reporter, stage_id, result, explanation)
    await reporter.rebuild(
        from_build_index=attempt,
        to_build_index=attempt + 1,
        reason_code=REASON_MODEL_INTERPRETATION_ERROR,
        message=_short(explanation.hypothesis or feedback[0]),
    )
    return {
        "result": result,
        "explanation": explanation,
        "problems": feedback,
        "rebuilds": attempt + 1,
        "route": ROUTE_TO_REBUILD,
    }


async def _finish_explain_stage(
    reporter: StageReporter,
    stage_id: str,
    result: VerificationResult,
    explanation: VerificationExplanation,
) -> None:
    """Закрыть этап объяснения честным исходом.

    Нарушение без гипотезы означает, что объяснение не получилось и остался
    шаблон: это провал этапа, а не тихий успех.
    """
    if result.status is not VerificationStatus.PROPERTY_VIOLATED:
        await reporter.finish(
            stage_id, state="SUCCEEDED", message="Объяснение не требуется: нарушений нет"
        )
        return
    if explanation.hypothesis is None:
        await reporter.finish(
            stage_id,
            state="FAILED",
            reason_code=REASON_LLM_UNAVAILABLE,
            message="Объяснение не получено, показан шаблонный текст",
        )
        return
    await reporter.finish(stage_id, state="SUCCEEDED", message="Контрпример объяснён")


def _agent_misread(result: VerificationResult, explanation: VerificationExplanation) -> bool:
    """Нарушение относится к модели, а не к требованию?"""
    return (
        result.status is VerificationStatus.PROPERTY_VIOLATED
        and explanation.root_cause is RootCause.AGENT_ERROR
    )


def _semantic_feedback(
    result: VerificationResult,
    explanation: VerificationExplanation,
) -> list[str]:
    """Замечание объяснения в форме, пригодной для перестройки модели."""
    hypothesis = (explanation.hypothesis or explanation.business_summary).strip()
    subject = f"Свойство {result.property_id}: " if result.property_id else ""
    return [
        f"{subject}объяснение признало ошибку модели, а не требования. {hypothesis}",
        "Перестрой модель так, чтобы формула каждого свойства означала ровно то, "
        "что написано в его description и source_reference. Если свойство связывает "
        "два признака, заведи для них отдельные переменные, а не один enum.",
    ]


def _finish(state: CycleState) -> dict[str, Any]:
    """Собрать итог итерации из состояния графа."""
    result = state["result"]
    explanation = state["explanation"]
    if _agent_misread(result, explanation):
        # Вопрос к требованию здесь не по адресу: модель ошиблась сама.
        explanation = explanation.model_copy(update={"question": None})
    return {
        "final": Iteration(
            status=result.status,
            model=state["model"],
            result=result,
            explanation=explanation,
            decision=decide(result.status, explanation.root_cause),
            gate_problems=tuple(state.get("problems", [])),
            rebuilds=state.get("rebuilds", 0),
            generation=state.get("generation"),
        )
    }


def _fail(state: CycleState) -> dict[str, Any]:
    """Завершить итерацию честным ``AGENT_ERROR``."""
    return {
        "final": _agent_failed(
            state.get("problems", []),
            state.get("rebuilds", 0),
            state.get("generation"),
        ),
    }


async def _explain(
    client: LLMClient,
    *,
    requirement_text: str,
    model: BehavioralModel,
    result: VerificationResult,
    limits: CycleLimits,
    reasoning: bool | None = None,
) -> tuple[VerificationResult, VerificationExplanation]:
    """Объяснить нарушение на языке требований либо оставить честный шаблон.

    Модель зовётся только при нарушении: у остальных статусов сценария нет, а
    пересказ отказа грозит выдать его за успех.
    """
    fallback = VerificationExplanation(business_summary=summary_for(result.status))
    if result.status is not VerificationStatus.PROPERTY_VIOLATED:
        return result, fallback
    try:
        answered = await explain_result(
            client,
            requirement_text=requirement_text,
            model=model,
            result=result,
            attempts=limits.explanation_attempts,
            reasoning=reasoning,
        )
    except (LLMError, ValidationError) as error:
        logger.warning("объяснение контрпримера не получено, остаётся шаблон: %s", error)
        return result, fallback
    enriched = result.model_copy(update={"related_requirements": answered.related_requirements})
    return enriched, answered.explanation


def _agent_failed(
    problems: list[str], rebuilds: int, generation: GenerationProfile | None
) -> Iteration:
    """Итерация, на которой агент не смог построить пригодную модель."""
    detail = "; ".join(problems) or "агент не вернул пригодную модель"
    result = VerificationResult(
        status=VerificationStatus.AGENT_ERROR,
        engine=ENGINE_WHEN_AGENT_FAILED,
        error_detail=detail,
    )
    return Iteration(
        status=VerificationStatus.AGENT_ERROR,
        model=None,
        result=result,
        explanation=VerificationExplanation(
            business_summary=summary_for(VerificationStatus.AGENT_ERROR)
        ),
        decision=AnalysisDecision.STOP,
        gate_problems=tuple(problems),
        rebuilds=rebuilds,
        generation=generation,
    )
