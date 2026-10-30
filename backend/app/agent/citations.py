"""Цитаты из текста требования.

Цитата — это дословный фрагмент исходного текста. Проверяется она в двух местах:
когда агент объясняет контрпример и когда модель проходит ворота перед движком.
Поэтому правило и нормализация живут здесь, а не дублируются в двух модулях.
"""

from __future__ import annotations

MIN_QUOTE_LENGTH = 12
"""Минимальная длина нормализованной цитаты.

Короткая строка вроде «и» или «заявка» технически является подстрокой, но не
подтверждает правило. Двенадцать символов отсекают такие ссылки, оставляя
возможность цитировать короткие, но содержательные начала фраз.
"""

MIN_QUOTE_WORDS = 2
"""Минимум слов в цитате: одно длинное слово тоже не подтверждает правило."""


def normalize(text: str) -> str:
    """Свести пробелы, чтобы цитата не ломалась на переносах строк."""
    return " ".join(text.split())


def is_quote(requirement_text: str, quote: str) -> bool:
    """Подтверждает ли цитата фрагмент текста требования.

    Цитата должна быть не только подстрокой, но и достаточно длинной, чтобы
    подтверждать правило, и начинаться/заканчиваться на границе слова. Иначе
    одна буква или обрывок слова проходили бы ворота.

    Args:
        requirement_text: Исходный текст требования.
        quote: Проверяемая цитата.

    Returns:
        ``True``, если цитата пригодна как ссылка на текст.
    """
    return quote_issue(requirement_text, quote) is None


def quote_issue(requirement_text: str, quote: str) -> str | None:
    """Объяснить, почему цитата не подтверждает текст, или вернуть ``None``.

    Отдельная функция нужна, чтобы ворота и объяснение показывали причину:
    слишком короткая цитата, цитата из одного слова и отсутствующий фрагмент —
    разные ошибки.
    """
    fragment = normalize(quote)
    if len(fragment) < MIN_QUOTE_LENGTH:
        return f"цитата слишком короткая: минимум {MIN_QUOTE_LENGTH} символов"
    if len(fragment.split()) < MIN_QUOTE_WORDS:
        return f"цитата должна содержать минимум {MIN_QUOTE_WORDS} слова"
    if not _contains_at_word_boundaries(normalize(requirement_text), fragment):
        return "цитата не встречается в тексте требования"
    return None


def _contains_at_word_boundaries(text: str, fragment: str) -> bool:
    """Найти фрагмент, не разрывающий слово с той или иной стороны."""
    start = text.find(fragment)
    while start != -1:
        end = start + len(fragment)
        left_ok = not _is_word_char(fragment[0]) or start == 0 or not _is_word_char(text[start - 1])
        right_ok = (
            not _is_word_char(fragment[-1]) or end == len(text) or not _is_word_char(text[end])
        )
        if left_ok and right_ok:
            return True
        start = text.find(fragment, start + 1)
    return False


def _is_word_char(char: str) -> bool:
    """Считать буквы, цифры и подчёркивание частью слова."""
    return char.isalnum() or char == "_"
