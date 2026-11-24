"""Обратимое представление Unicode-строк в ASCII-спецификации TLC."""

_PREFIX = "__aa_utf8_"


def encode_string(value: str) -> str:
    """Сохранить различие строк, включая совпадение со служебным префиксом."""
    if value.isascii() and not value.startswith(_PREFIX):
        return value
    return _PREFIX + value.encode("utf-8").hex()


def decode_string(value: str) -> str:
    """Вернуть исходную строку из вывода TLC."""
    if not value.startswith(_PREFIX):
        return value
    try:
        return bytes.fromhex(value[len(_PREFIX) :]).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return value
