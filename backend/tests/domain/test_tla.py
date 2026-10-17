"""Сборка спецификации TLA+ из BehavioralModel.

Тесты чистые: ни Java, ни БД. Проверяют текст, который увидит SANY, поэтому
ошибка здесь поймается до запуска перебора, а не после минуты ожидания.

Модель кейса берётся из ``tests.domain.case_examples`` — общий фикстур, чтобы
модель не расходилась между доменными и движковыми тестами.
"""

from typing import Any

import pytest

from app.domain.behavioral_model import BehavioralModel, Property
from app.domain.tla import compile_model
from tests.domain.case_examples import case_model, fixed_model

MODULE_END = "=" * 71


def _model(document: dict[str, Any] | None = None) -> BehavioralModel:
    return BehavioralModel.model_validate(document or case_model())


def _property(model: BehavioralModel, prop_type: str) -> Property:
    """Свойство заданного типа из кейса: в модели есть по одному каждого типа."""
    return next(prop for prop in model.properties if prop.type == prop_type)


def test_declares_every_variable_in_the_variables_line() -> None:
    """Все переменные модели попадают в ``VARIABLES`` и в ``Spec``."""
    model = _model()

    spec = compile_model(model, _property(model, "invariant"))

    variables = "status, approved, cancelled, attempts"
    assert f"VARIABLES {variables}" in spec.tla
    assert f"[Next]_<<{variables}>>" in spec.tla


def test_writes_initial_values_with_tla_literals() -> None:
    """Начальное состояние пишется литералами TLA+, а не значениями JSON."""
    model = _model()

    spec = compile_model(model, _property(model, "invariant"))

    assert '/\\ status = "Created"' in spec.tla
    assert "/\\ approved = FALSE" in spec.tla
    assert "/\\ attempts = 0" in spec.tla


def test_assigns_untouched_variables_to_themselves() -> None:
    """Переход присваивает все переменные: не затронутые сохраняют значение.

    Иначе результат перехода зависит от того, как TLC добрал остальные значения,
    и модель перестаёт описывать ровно то, что написано в DSL.
    """
    model = _model()

    spec = compile_model(model, _property(model, "invariant"))

    approve = spec.tla.split("Approve ==")[1].split("\n\nCancel ==")[0]
    assert "/\\ cancelled' = cancelled" in approve
    assert "/\\ attempts' = attempts" in approve


def test_lists_every_transition_in_next() -> None:
    """``Next`` перечисляет все переходы — иначе часть модели не проверяется."""
    model = _model()

    spec = compile_model(model, _property(model, "invariant"))

    for transition in model.transitions:
        assert f"\\/ {transition.name}" in spec.tla


def test_forbidden_state_becomes_negated_invariant() -> None:
    """``forbidden_state`` компилируется в инвариант с отрицанием."""
    model = _model()
    prop = _property(model, "forbidden_state")

    spec = compile_model(model, prop)

    assert f"{prop.id} == ~((" in spec.tla
    assert spec.cfg == f"SPECIFICATION Spec\nINVARIANT {prop.id}\n"


def test_parenthesizes_conjuncts_before_negation() -> None:
    r"""В TLA+ ``~`` связывает крепче ``/\``: без скобок отрицается только первый член."""
    model = _model()
    prop = _property(model, "forbidden_state")

    spec = compile_model(model, prop)

    definition = next(line for line in spec.tla.splitlines() if line.startswith(prop.id))
    assert definition.count("(") == definition.count(")") >= 2


def test_invariant_is_configured_by_name_only() -> None:
    """В конфигурации у инварианта только имя.

    ``INVARIANT P1 == выражение`` в .cfg — не синтаксис TLC: оператор должен быть
    определён в модуле, иначе движок отвечает ошибкой и прогон не начинается.
    """
    model = _model()
    prop = _property(model, "invariant")

    spec = compile_model(model, prop)

    assert spec.cfg.splitlines() == ["SPECIFICATION Spec", f"INVARIANT {prop.id}"]


def test_membership_expression_becomes_tla_set() -> None:
    """Домен ``in`` переносится в множество TLA+ вместе со значениями."""
    model = _model()

    spec = compile_model(model, _property(model, "invariant"))

    assert "\\in {" in spec.tla


def test_reachable_is_checked_by_negated_invariant() -> None:
    """``reachable`` проверяется отрицанием, а вердикт читается наоборот.

    Формула ``<>P`` тут не работает: она требует достижимости на каждом поведении,
    а спецификация допускает вечное застывание в начальном состоянии, поэтому
    ``<>P`` опровергается всегда, что бы ни говорила модель.
    """
    model = _model()
    prop = _property(model, "reachable")

    spec = compile_model(model, prop)

    assert f"{prop.id} == ~(" in spec.tla
    assert spec.polarity == "negated"
    assert spec.cfg.splitlines() == ["SPECIFICATION Spec", f"INVARIANT {prop.id}"]


def test_deadlock_free_becomes_enabled_invariant() -> None:
    """``deadlock_free`` — инвариант над ``ENABLED Next``, а не отдельный флаг.

    ``ENABLED <<Next>>`` здесь не подходит: ``<<...>>`` — оператор подстановки,
    и TLC не может его вычислить, отвечая ошибкой вместо проверки.
    """
    model = _model()
    prop = _property(model, "deadlock_free")

    spec = compile_model(model, prop)

    assert spec.tla.endswith(f"{prop.id} == ENABLED Next\n\n{MODULE_END}\n")
    assert spec.cfg.splitlines() == ["SPECIFICATION Spec", f"INVARIANT {prop.id}"]


def test_keeps_only_the_requested_property() -> None:
    """В спецификацию попадает одно свойство: у результата одно ``property_id``."""
    model = _model()

    spec = compile_model(model, _property(model, "invariant"))

    assert len(spec.cfg.splitlines()) == 2
    for other in model.properties[1:]:
        assert other.id not in spec.cfg


def test_fixed_model_writes_the_resetting_effect() -> None:
    """Исправленная модель кейса действительно сбрасывает ``approved`` в ``Cancel``."""
    model = _model(fixed_model())

    spec = compile_model(model, _property(model, "forbidden_state"))

    cancel = spec.tla.split("Cancel ==")[1].split("\n\nExecute ==")[0]
    assert "/\\ approved' = FALSE" in cancel


def test_escapes_quotes_in_enum_values() -> None:
    """Кавычка внутри значения enum не разрывает литерал TLA+."""
    document = dict(case_model())
    document["variables"] = [
        {"name": "note", "type": "enum", "values": ['say "hi"', "plain"]},
        *document["variables"],
    ]
    document["initial"] = {"note": 'say "hi"', **document["initial"]}
    document["transitions"] = [
        {
            "name": "Note",
            "guard": {"eq": [{"var": "note"}, 'say "hi"']},
            "effects": [{"set": ["note", "plain"]}],
        },
        *document["transitions"],
    ]
    model = _model(document)

    spec = compile_model(model, _property(model, "invariant"))

    assert r'note = "say \"hi\""' in spec.tla


def test_rejects_property_from_another_model() -> None:
    """Свойство чужой модели в спецификацию не попадает."""
    model = _model()

    with pytest.raises(KeyError):
        compile_model(model, Property(id="P9", type="deadlock_free"))
