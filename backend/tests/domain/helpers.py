"""Общие утверждения тестов доменного слоя."""

from typing import Any

import pytest
from pydantic import BaseModel, ValidationError


def assert_rejected[ModelT: BaseModel](model: type[ModelT], document: Any, fragment: str) -> None:
    """Убедиться, что документ отвергнут и что сработала именно нужная проверка.

    Проверки не только «что-то упало»: фрагмент сообщения подтверждает конкретное
    правило. Иначе тест на уникальность имён прошёл бы из-за опечатки в домене.

    Args:
        model: класс Pydantic, который должен отвергнуть документ.
        document: проверяемый документ.
        fragment: ожидаемый фрагмент текста ошибки.

    Raises:
        AssertionError: если документ принят либо ошибка оказалась другой.
    """
    with pytest.raises(ValidationError) as caught:
        model.model_validate(document)
    message = str(caught.value)
    assert fragment in message, f"ожидалось {fragment!r} в сообщении, получено:\n{message}"
