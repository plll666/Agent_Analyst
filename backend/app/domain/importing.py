"""Извлечение текста требования из TXT и DOCX.

Домен, а не адаптер: здесь только байты файла и готовые фрагменты, без БД и
без HTTP. Правила из контракта спринта 3, раздел 2.2:

* текст собирается из фрагментов, разделитель — ``\\n\\n``;
* смещения считаются в Unicode-кодовых точках по ``raw_text``, начало
  включено, конец исключён, поэтому ``raw_text[start:end]`` — точный текст
  фрагмента;
* незаметное обрезание запрещено: исключённое содержимое даёт предупреждение
  ``CONTENT_OMITTED``, а пустой или сломанный файл — ошибку с кодом из
  контракта.

Ошибки поднимаются как :class:`ImportFailure` с кодом и сообщением: HTTP-слой
просто кладёт их в общий конверт ошибок.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Форматы и коды ошибок контракта (раздел 2.2).
FORMAT_TXT = "txt"
FORMAT_DOCX = "docx"
SUPPORTED_FORMATS: tuple[str, ...] = (FORMAT_TXT, FORMAT_DOCX)

FILE_TOO_LARGE = "FILE_TOO_LARGE"
UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE"
EMPTY_DOCUMENT = "EMPTY_DOCUMENT"
INVALID_DOCUMENT = "INVALID_DOCUMENT"
UNSUPPORTED_ENCODING = "UNSUPPORTED_ENCODING"
TEXT_TOO_LARGE = "TEXT_TOO_LARGE"

CONTENT_OMITTED = "CONTENT_OMITTED"

_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class ImportFailure(Exception):
    """Файл не прошёл импорт: код из контракта и сообщение для пользователя."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class Fragment(BaseModel):
    """Кусок извлечённого текста со смещениями в ``raw_text``."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    kind: Literal["paragraph", "table_cell"]
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    source_locator: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def validate_bounds(self) -> Fragment:
        """Конец не может опережать начало: смещения считаются по одному тексту."""
        if self.end < self.start:
            raise ValueError(f"фрагмент {self.id}: end={self.end} меньше start={self.start}")
        return self


class ImportWarning(BaseModel):
    """Предупреждение о содержимом, которое не попало в текст."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=500)


class ExtractedDocument(BaseModel):
    """Результат разбора файла: текст, фрагменты и предупреждения."""

    model_config = ConfigDict(extra="forbid")

    raw_text: str
    fragments: tuple[Fragment, ...]
    warnings: tuple[ImportWarning, ...] = ()


def detect_format(filename: str) -> str:
    """Определить формат по расширению файла.

    Args:
        filename: Имя загруженного файла.

    Returns:
        ``txt`` либо ``docx``.

    Raises:
        ImportFailure: расширение не поддерживается (415).
    """
    suffix = Path(filename).suffix.lower()
    if suffix == ".txt":
        return FORMAT_TXT
    if suffix == ".docx":
        return FORMAT_DOCX
    raise ImportFailure(
        UNSUPPORTED_FILE_TYPE,
        f"Поддерживаются только TXT и DOCX, а получен файл {Path(filename).name or '(без имени)'}",
    )


def extract(
    file_format: str,
    data: bytes,
    *,
    max_text_chars: int,
    max_unpacked_bytes: int,
    max_archive_entries: int,
) -> ExtractedDocument:
    """Разобрать файл и вернуть текст с фрагментами.

    Args:
        file_format: ``txt`` или ``docx`` — уже проверенное расширение.
        data: Содержимое файла целиком.
        max_text_chars: Предел длины извлечённого текста.
        max_unpacked_bytes: Предел распакованного объёма DOCX.
        max_archive_entries: Предел числа записей архива DOCX.

    Returns:
        Извлечённый документ.

    Raises:
        ImportFailure: файл пустой, сломанный, слишком большой или в другой
            кодировке — с кодом из контракта.
    """
    if file_format == FORMAT_TXT:
        raw_text, fragments = _extract_txt(data)
        warnings: tuple[ImportWarning, ...] = ()
    elif file_format == FORMAT_DOCX:
        raw_text, fragments, docx_warnings = _extract_docx(
            data, max_unpacked_bytes=max_unpacked_bytes, max_entries=max_archive_entries
        )
        warnings = tuple(docx_warnings)
    else:  # защита от неверного вызова, а не рабочий путь
        raise ImportFailure(UNSUPPORTED_FILE_TYPE, f"Неизвестный формат: {file_format}")

    if not raw_text.strip():
        raise ImportFailure(EMPTY_DOCUMENT, "В файле нет текста: извлекать нечего")
    if len(raw_text) > max_text_chars:
        raise ImportFailure(
            TEXT_TOO_LARGE,
            f"Извлечённый текст — {len(raw_text)} символов при лимите {max_text_chars}",
        )
    return ExtractedDocument(raw_text=raw_text, fragments=tuple(fragments), warnings=warnings)


def rebuild_fragments(text: str) -> tuple[Fragment, ...]:
    """Пересобрать фрагменты под подтверждённый пользователем текст.

    Срабатывает, когда текст после предпросмотра изменён: сопоставление
    отредактированного фрагмента с абзацем или ячейкой файла в спринте не
    обещается, поэтому ``source_locator`` пуст. Смещения считаются по переданному
    тексту, и ``raw_text[start:end]`` остаётся точным.

    Args:
        text: Подтверждённый текст требования.

    Returns:
        Фрагменты по непустым строкам текста.
    """
    fragments: list[Fragment] = []
    offset = 0
    paragraph = 0
    for line in text.split("\n"):
        if line.strip():
            paragraph += 1
            fragments.append(
                Fragment(
                    id=f"p{paragraph}",
                    kind="paragraph",
                    start=offset,
                    end=offset + len(line),
                    source_locator=None,
                )
            )
        offset += len(line) + 1
    return tuple(fragments)


def _extract_txt(data: bytes) -> tuple[str, list[Fragment]]:
    """Разобрать TXT: UTF-8, BOM разрешён, другие кодировки — ошибка.

    Args:
        data: Содержимое файла.

    Returns:
        Текст и фрагменты по непустым строкам.

    Raises:
        ImportFailure: файл не в UTF-8 (422 UNSUPPORTED_ENCODING).
    """
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ImportFailure(
            UNSUPPORTED_ENCODING,
            "TXT должен быть в UTF-8 (BOM допустим): файл не декодируется "
            f"как UTF-8 в байте {error.start}",
        ) from error

    if "\x00" in text:
        raise ImportFailure(INVALID_DOCUMENT, "TXT содержит двоичные данные")

    text = _normalize_newlines(text)
    fragments: list[Fragment] = []
    pieces: list[str] = []
    paragraph = 0
    for line in text.split("\n"):
        if line.strip():
            paragraph += 1
            pieces.append(line)
            fragments.append(
                Fragment(
                    id=f"p{paragraph}",
                    kind="paragraph",
                    start=0,  # пересчитывается ниже по склеенному тексту
                    end=len(line),
                    source_locator=f"body/paragraph/{paragraph}",
                )
            )
    _rebase(fragments, pieces)
    return "\n\n".join(pieces), fragments


def _extract_docx(
    data: bytes, *, max_unpacked_bytes: int, max_entries: int
) -> tuple[str, list[Fragment], list[ImportWarning]]:
    """Разобрать DOCX: абзацы и ячейки таблиц основного тела в порядке документа.

    Args:
        data: Содержимое файла.
        max_unpacked_bytes: Предел распакованного объёма архива.
        max_entries: Предел числа записей архива.

    Returns:
        Текст, фрагменты и предупреждения о невключённом содержимом.

    Raises:
        ImportFailure: архив небезопасен или документ повреждён.
    """
    _guard_archive(data, max_unpacked_bytes=max_unpacked_bytes, max_entries=max_entries)
    try:
        from docx import Document
        from docx.table import Table, _Cell
        from docx.text.paragraph import Paragraph

        document = Document(io.BytesIO(data))
        body = document.element.body
        pieces: list[str] = []
        fragments: list[Fragment] = []
        paragraph_index = 0
        table_index = 0
        cell_index = 0

        for child in body.iterchildren():
            if child.tag == f"{_W_NS}p":
                text = Paragraph(child, document).text
                if not text.strip():
                    continue
                paragraph_index += 1
                pieces.append(text)
                fragments.append(
                    Fragment(
                        id=f"p{paragraph_index}",
                        kind="paragraph",
                        start=0,
                        end=len(text),
                        source_locator=f"body/paragraph/{paragraph_index}",
                    )
                )
            elif child.tag == f"{_W_NS}tbl":
                table_index += 1
                table = Table(child, document)
                for row_number, row in enumerate(table._tbl.findall(f"{_W_NS}tr"), start=1):
                    for cell_number, cell_element in enumerate(row.findall(f"{_W_NS}tc"), start=1):
                        text = _Cell(cell_element, table).text
                        if not text.strip():
                            continue
                        cell_index += 1
                        pieces.append(text)
                        fragments.append(
                            Fragment(
                                id=f"tc{cell_index}",
                                kind="table_cell",
                                start=0,
                                end=len(text),
                                source_locator=(
                                    f"body/table/{table_index}/row/{row_number}/cell/{cell_number}"
                                ),
                            )
                        )
    except ImportFailure:
        raise
    except Exception as error:  # noqa: BLE001 - любой сбой разбора это «повреждённый файл»
        raise ImportFailure(
            INVALID_DOCUMENT,
            "DOCX не разобран: файл повреждён или не является документом Word",
        ) from error

    warnings = _omitted_content_warnings(document)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if "word/comments.xml" in archive.namelist():
            warnings.append(
                ImportWarning(
                    code=CONTENT_OMITTED,
                    message="Комментарии не включены в извлечённый текст",
                )
            )
    _rebase(fragments, pieces)
    return "\n\n".join(pieces), fragments, warnings


def _rebase(fragments: list[Fragment], pieces: list[str]) -> None:
    """Пересчитать смещения фрагментов по склеенному тексту.

    Фрагменты собираются по одному тексту, но смещения считать удобнее после
    склейки: разделитель ровно ``\\n\\n``, и смещение каждого фрагмента — длина
    всех предыдущих плюс разделители.

    Args:
        fragments: Фрагменты в порядке текста, смещения будут перезаписаны.
        pieces: Тексты фрагментов в том же порядке.
    """
    offset = 0
    for fragment, piece in zip(fragments, pieces, strict=True):
        fragment.start = offset
        fragment.end = offset + len(piece)
        offset = fragment.end + 2  # "\n\n"


def _normalize_newlines(text: str) -> str:
    """Привести ``\\r\\n`` и ``\\r`` к ``\\n``: фрагменты живут в одном тексте."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _guard_archive(data: bytes, *, max_unpacked_bytes: int, max_entries: int) -> None:
    """Отклонить небезопасный или не-DOCX архив до разбора.

    Args:
        data: Содержимое файла.
        max_unpacked_bytes: Предел суммарного распакованного объёма.
        max_entries: Предел числа записей.

    Raises:
        ImportFailure: файл не архив, архив переборщил с объёмом или записями.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
    except zipfile.BadZipFile as error:
        raise ImportFailure(
            INVALID_DOCUMENT, "Файл не открывается как DOCX: архив повреждён"
        ) from error

    if len(infos) > max_entries:
        raise ImportFailure(
            INVALID_DOCUMENT,
            f"В архиве {len(infos)} записей при лимите {max_entries}: разбор отклонён",
        )
    unpacked = sum(info.file_size for info in infos)
    if unpacked > max_unpacked_bytes:
        raise ImportFailure(
            FILE_TOO_LARGE,
            f"Распакованный документ — {unpacked} байт при лимите {max_unpacked_bytes}",
        )
    if any(info.flag_bits & 0x1 for info in infos):
        raise ImportFailure(INVALID_DOCUMENT, "Зашифрованный DOCX не поддерживается")
    if "word/document.xml" not in {info.filename for info in infos}:
        raise ImportFailure(
            INVALID_DOCUMENT, "В архиве нет word/document.xml: это не документ Word"
        )


def _omitted_content_warnings(document: object) -> list[ImportWarning]:
    """Предупредить о содержимом, которое в текст не попало.

    Колонтитулы, комментарии и изображения в объём спринта не входят, но
    молча выбросить их нельзя: пользователь должен знать, что текст неполный.

    Args:
        document: Разобранный документ python-docx.

    Returns:
        Список предупреждений; пустой, если исключённого содержимого нет.
    """
    from docx.oxml.ns import qn

    element = document.element  # type: ignore[attr-defined]
    warnings: list[ImportWarning] = []
    if element.findall(f".//{qn('w:drawing')}") or element.findall(f".//{qn('w:pict')}"):
        warnings.append(
            ImportWarning(
                code=CONTENT_OMITTED, message="Изображения не включены в извлечённый текст"
            )
        )
    if element.findall(f".//{qn('w:txbxContent')}"):
        warnings.append(
            ImportWarning(
                code=CONTENT_OMITTED,
                message="Текстовые блоки в текстовых полях не включены в извлечённый текст",
            )
        )
    if element.findall(f".//{qn('w:sectPr')}/{qn('w:headerReference')}") or element.findall(
        f".//{qn('w:sectPr')}/{qn('w:footerReference')}"
    ):
        warnings.append(
            ImportWarning(
                code=CONTENT_OMITTED, message="Колонтитулы не включены в извлечённый текст"
            )
        )
    return warnings
