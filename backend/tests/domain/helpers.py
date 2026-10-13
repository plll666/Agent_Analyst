from typing import Any

import pytest
from pydantic import BaseModel, ValidationError


def assert_rejected[ModelT: BaseModel](model: type[ModelT], document: Any, fragment: str) -> None:
    """Убедиться, что документ отвергнут именно нужной проверкой."""
    with pytest.raises(ValidationError) as caught:
        model.model_validate(document)
    message = str(caught.value)
    assert fragment in message, f"ожидалось {fragment!r} в сообщении, получено:\n{message}"
