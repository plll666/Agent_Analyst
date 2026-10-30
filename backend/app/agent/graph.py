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
Запись в базу делает вызывающая сторона.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import lru_cache, partial
from typing import Any, TypedDict, cast

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from app.agent import self_check
from app.agent.explainer import explain_result
from app.agent.llm import LLMClient, LLMError, LLMResponseError
from app.agent.modeler import build_model
from app.domain.behavioral_model import BehavioralModel, Property
from app.domain.decision import AnalysisDecision, decide
from app.domain.explanation import summary_for
from app.domain.verdict import combine
from app.domain.verification import (
    RootCause,
    VerificationExplanation,
    VerificationResult,
    VerificationStatus,
)

logger = logging.getLogger(__name__)

CheckProperty = Callable[[BehavioralModel, Property], Awaitable[VerificationResult]]
ModelHandler = Callable[[BehavioralModel], Awaitable[None]]

ENGINE_WHEN_AGENT_FAILED = "AGENT"

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
    max_rebuilds: int = 2
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
    """

    status: VerificationStatus
    model: BehavioralModel | None
    result: VerificationResult | None
    explanation: VerificationExplanation
    decision: AnalysisDecision
    gate_problems: tuple[str, ...] = ()
    rebuilds: int = 0


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
        builder.add_node(f"build_{attempt}", _build)
        builder.add_node(f"gate_{attempt}", partial(_gate, attempt=attempt))
        builder.add_node(f"check_{attempt}", _check)
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


def _route(state: CycleState) -> str:
    """Прочитать маршрут, который выбрал предыдущий узел."""
    return state["route"]


async def _build(state: CycleState) -> dict[str, Any]:
    """Построить модель; и первая сборка, и перестроение получают все попытки.

    Одна попытка на перестроение оказалась хрупкой: невалидный структурный
    ответ модели обрывал цикл, хотя следующая попытка обычно исправляла
    документ. Поэтому ``build_attempts`` — бюджет любого построения, а не
    только первого.
    """
    limits = state["limits"]
    problems = state.get("problems", [])
    try:
        model = await build_model(
            state["client"],
            requirement_text=state["requirement_text"],
            attempts=limits.build_attempts,
            feedback=problems,
            reasoning=state.get("reasoning"),
        )
    except LLMResponseError as error:
        # Сохраняем нарушения схемы: без них в UI видно только «не ответила»,
        # а причина (какое поле не то) теряется.
        return {
            "model": None,
            "problems": [*problems, *error.problems],
            "route": ROUTE_TO_FAIL,
        }
    except (LLMError, ValidationError) as error:
        return {
            "model": None,
            "problems": [*problems, str(error)],
            "route": ROUTE_TO_FAIL,
        }
    return {"model": model, "route": ROUTE_TO_GATE}


async def _gate(state: CycleState, *, attempt: int) -> dict[str, Any]:
    """Проверить модель воротами и решить, что делать дальше."""
    model = state["model"]
    if model is None:  # защита от неверной сборки графа, а не рабочий путь
        return {"route": ROUTE_TO_FAIL}
    gate = self_check.check(model, state["requirement_text"])
    previous = state.get("problems", [])

    if not gate:
        handler = state.get("on_model")
        if handler is not None:
            await handler(model)
        return {"route": ROUTE_TO_CHECK}

    if gate == previous:
        logger.warning("ворота вернули те же замечания второй раз подряд: %s", "; ".join(gate))
        return {"problems": gate, "route": ROUTE_TO_FAIL}

    rebuilds = attempt + 1
    if attempt >= state["limits"].max_rebuilds:
        return {"problems": gate, "rebuilds": rebuilds, "route": ROUTE_TO_FAIL}
    return {"problems": gate, "rebuilds": rebuilds, "route": ROUTE_TO_REBUILD}


async def _check(state: CycleState) -> dict[str, Any]:
    """Проверить все свойства модели детерминированным движком."""
    model = state["model"]
    if model is None:  # недостижимо: до check ведёт только пройденный gate
        raise RuntimeError("граф дошёл до проверки без модели")
    results = [await state["check_property"](model, prop) for prop in model.properties]
    return {"result": combine(results)}


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
    result, explanation = await _explain(
        state["client"],
        requirement_text=state["requirement_text"],
        model=model,
        result=state["result"],
        limits=state["limits"],
        reasoning=state.get("reasoning"),
    )

    if not _agent_misread(result, explanation):
        return {"result": result, "explanation": explanation, "route": ROUTE_TO_FINISH}

    feedback = _semantic_feedback(result, explanation)
    previous = state.get("problems", [])
    if feedback == previous:
        logger.warning("объяснение повторило те же замечания к модели: %s", "; ".join(feedback))
        return {
            "result": result,
            "explanation": explanation,
            "problems": feedback,
            "route": ROUTE_TO_FINISH,
        }
    if attempt >= state["limits"].max_rebuilds:
        logger.warning("объяснение признало ошибку модели, но лимит перестроений исчерпан")
        return {
            "result": result,
            "explanation": explanation,
            "problems": feedback,
            "route": ROUTE_TO_FINISH,
        }

    logger.info("объяснение признало ошибку модели, перестраиваю: %s", explanation.hypothesis)
    return {
        "result": result,
        "explanation": explanation,
        "problems": feedback,
        "rebuilds": attempt + 1,
        "route": ROUTE_TO_REBUILD,
    }


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
        )
    }


def _fail(state: CycleState) -> dict[str, Any]:
    """Завершить итерацию честным ``AGENT_ERROR``."""
    return {
        "final": _agent_failed(state.get("problems", []), state.get("rebuilds", 0)),
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


def _agent_failed(problems: list[str], rebuilds: int) -> Iteration:
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
    )
