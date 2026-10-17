from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, SerializerFunctionWrapHandler, model_serializer


def _without_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _without_none(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_without_none(item) for item in value]
    return value


class WireModel(BaseModel):
    """Модель, у которой ``null`` не попадает в JSON.

    Декодер фронта отсутствующий ключ читает как ``null`` или как значение по
    умолчанию, но явный ``null`` в ``values`` считает ошибкой. Поэтому на проводе
    null не ходит, и ``model_dump()`` возвращает готовый документ без правок.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_serializer(mode="wrap")
    def strip_none(self, handler: SerializerFunctionWrapHandler) -> Any:
        return _without_none(handler(self))
