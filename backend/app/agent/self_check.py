"""Ворота перед вызовом движка: модель готова к проверке?

Проверяются два свойства модели, и оба — про её честность, а не про красоту.

**Правила модели должны быть из текста.** У каждого перехода и каждого свойства
есть ссылка на требование, и это дословный фрагмент текста. Если ссылки нет или
она выдумана, элемент придуман агентом. Именно так исчезает контрпример: модель
«уточняется» до состояния, в котором нарушать нечего, — и система радостно
сообщает, что нарушений нет. У переменной ссылка необязательна (состояние могло
быть и не названо в тексте), но если она есть, она тоже должна быть из текста.

**Свойство должно зависеть от поведения.** Свойство-константа истинно при любом
состоянии: формально проверка даёт «нарушений нет», а на самом деле не проверено
ничего. Такой дешёвый успех опаснее явной ошибки, поэтому он отсекается здесь.

Модуль чистый: ни БД, ни сети, ни LLM. Проверку можно прогнать на любой модели и
на любом тексте требования.
"""

from __future__ import annotations

from app.agent.citations import quote_issue
from app.domain.behavioral_model import BehavioralModel
from app.domain.expressions import AndExpr, Effect, EqExpr, Expression, InExpr, VarExpr

_EXPRESSION_NODES = (VarExpr, AndExpr, EqExpr, InExpr)


def check(model: BehavioralModel, requirement_text: str) -> list[str]:
    """Перечислить, что мешает проверить модель как есть.

    Args:
        model: Построенная агентом модель.
        requirement_text: Текст требования, по которому она построена.

    Returns:
        Список замечаний; пустой означает, что модель можно отдавать движку.
    """
    problems: list[str] = []
    problems.extend(_rule_citation_problems(model, requirement_text))
    problems.extend(_variable_citation_problems(model, requirement_text))
    problems.extend(_trivial_property_problems(model))
    return problems


def _rule_citation_problems(model: BehavioralModel, requirement_text: str) -> list[str]:
    """У перехода и у свойства цитата обязательна и должна быть из текста."""
    problems: list[str] = []
    for transition in model.transitions:
        problems.extend(
            _citation_problem(
                transition.source_reference, requirement_text, f"переход {transition.name!r}"
            )
        )
    for prop in model.properties:
        problems.extend(
            _citation_problem(prop.source_reference, requirement_text, f"свойство {prop.id!r}")
        )
    return problems


def _variable_citation_problems(model: BehavioralModel, requirement_text: str) -> list[str]:
    """У переменной цитата необязательна, но выдуманной быть не может."""
    problems: list[str] = []
    for variable in model.variables:
        if variable.source_reference is None:
            continue
        problems.extend(
            _citation_problem(
                variable.source_reference,
                requirement_text,
                f"переменная {variable.name!r}",
            )
        )
    return problems


def _citation_problem(citation: str | None, requirement_text: str, subject: str) -> list[str]:
    """Проверить одну ссылку на требование."""
    if citation is None or not citation.strip():
        return [
            f"{subject} не ссылается на текст требования: "
            "укажи дословную цитату, из которой правило взято"
        ]
    issue = quote_issue(requirement_text, citation)
    if issue is not None:
        return [
            f"{subject}: {issue}; цитата {citation.strip()!r}. "
            "Нужна дословная цитата из текста требования"
        ]
    return []


def _trivial_property_problems(model: BehavioralModel) -> list[str]:
    """Свойство должно зависеть от того, что меняется в модели."""
    changed = _changed_variables(model)
    problems: list[str] = []
    for prop in model.properties:
        if prop.expression is None:
            continue
        referenced = _variables_in_expression(prop.expression)
        if not referenced & changed:
            problems.append(
                f"свойство {prop.id!r} не зависит от поведения: "
                "оно истинно при любом состоянии, проверять в нём нечего"
            )
    return problems


def _changed_variables(model: BehavioralModel) -> set[str]:
    """Какие переменные вообще могут измениться."""
    changed: set[str] = set()
    for transition in model.transitions:
        for effect in transition.effects:
            changed.add(_effect_variable(effect))
    return changed


def _effect_variable(effect: Effect) -> str:
    """Имя переменной, которой присваивает эффект."""
    return effect.set[0]


def _variables_in_expression(expression: Expression) -> set[str]:
    """Какие переменные упоминает выражение."""
    if isinstance(expression, VarExpr):
        return {expression.name}
    if isinstance(expression, AndExpr):
        return set().union(*(_variables_in_expression(arg) for arg in expression.args))
    if isinstance(expression, EqExpr):
        return set().union(
            *(
                _variables_in_expression(arg)
                for arg in expression.args
                if isinstance(arg, _EXPRESSION_NODES)
            )
        )
    value = expression.value
    if isinstance(value, _EXPRESSION_NODES):
        return _variables_in_expression(value)
    return set()
