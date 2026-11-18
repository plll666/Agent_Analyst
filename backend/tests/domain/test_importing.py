"""Проверки извлечения текста и смещений подтверждаемой версии."""

import io

import pytest
from docx import Document

from app.domain.importing import (
    EMPTY_DOCUMENT,
    INVALID_DOCUMENT,
    TEXT_TOO_LARGE,
    ImportFailure,
    extract,
    rebuild_fragments,
)


def _extract(file_format: str, data: bytes, max_text_chars: int = 100):
    return extract(
        file_format,
        data,
        max_text_chars=max_text_chars,
        max_unpacked_bytes=64 * 1024 * 1024,
        max_archive_entries=1000,
    )


def test_docx_preserves_body_order_and_unicode_offsets() -> None:
    document = Document()
    document.add_paragraph("Заявка 😀")
    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "Отмена"
    stream = io.BytesIO()
    document.save(stream)

    extracted = _extract("docx", stream.getvalue())

    assert extracted.raw_text == "Заявка 😀\n\nОтмена"
    assert [part.kind for part in extracted.fragments] == ["paragraph", "table_cell"]
    assert [extracted.raw_text[part.start : part.end] for part in extracted.fragments] == [
        "Заявка 😀", "Отмена"
    ]
    assert extracted.fragments[1].source_locator == "body/table/1/row/1/cell/1"


def test_edited_text_gets_new_fragments_without_source_locators() -> None:
    text = "Новое правило\nИ ещё одно"
    fragments = rebuild_fragments(text)
    assert [text[part.start : part.end] for part in fragments] == [
        "Новое правило", "И ещё одно"
    ]
    assert all(part.source_locator is None for part in fragments)


@pytest.mark.parametrize(
    ("file_format", "data", "limit", "code"),
    [
        ("txt", b"", 100, EMPTY_DOCUMENT),
        ("txt", b"A\x00B", 100, INVALID_DOCUMENT),
        ("txt", b"Too long", 2, TEXT_TOO_LARGE),
        ("docx", b"not a document", 100, INVALID_DOCUMENT),
    ],
)
def test_rejects_invalid_or_oversized_documents(
    file_format: str, data: bytes, limit: int, code: str
) -> None:
    with pytest.raises(ImportFailure) as failure:
        _extract(file_format, data, limit)
    assert failure.value.code == code
