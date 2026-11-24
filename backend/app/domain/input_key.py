"""Канонический ключ входа прогона.

Контракт спринта 3, раздел 3.1. Ключ отвечает на вопрос «был ли уже такой
запуск»: два запроса с одинаковым ключом означают один и тот же вход, и
второй обычный запуск получает сохранённый результат вместо нового вызова
LLM и TLC.

Канонизация рекурсивно сортирует ключи JSON, сериализует в UTF-8 без
пробелов и одинаково представляет числа: иначе порядок полей в словаре
менял бы ключ. Текст требования в ключ не кладётся целиком — только хэш
сохранённого текста, чтобы ключ не выдавал содержимое наружу.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

# Версия алгоритма ключа: меняется при любом изменении состава или
# канонизации — прежние ключи перестают совпадать, и результат не
# переиспользуется молча.
KEY_ALGORITHM_VERSION = "input-key-1"


def canonical_json(payload: Mapping[str, Any]) -> bytes:
    """Каноническое представление документа ключа.

    Args:
        payload: Документ ключа: только JSON-типы.

    Returns:
        UTF-8 байты канонического JSON.
    """
    text = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return text.encode("utf-8")


def compute_input_key(payload: Mapping[str, Any]) -> str:
    """SHA-256 канонического JSON документа ключа.

    Args:
        payload: Документ ключа; ``KEY_ALGORITHM_VERSION`` добавляется сюда же.

    Returns:
        Строка вида ``sha256:<hex>``.
    """
    digest = hashlib.sha256(canonical_json(payload)).hexdigest()
    return f"sha256:{digest}"


def text_digest(text: str) -> str:
    """Хэш точного сохранённого текста требования для документа ключа."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
