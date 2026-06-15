from dataclasses import FrozenInstanceError
import inspect
import unicodedata

import pytest

from app.rag.cleaning.normalization import (
    CONTROL_CHARACTERS_REMOVED,
    LINE_ENDINGS_NORMALIZED,
    LIST_WHITESPACE_NORMALIZED,
    NBSP_NORMALIZED,
    PROSE_WHITESPACE_NORMALIZED,
    REPLACEMENT_CHARACTER_DETECTED,
    SUSPICIOUS_CONTROL_CHARACTERS_REMOVED,
    TABLE_CELLS_NORMALIZED,
    UNICODE_NFC,
    NormalizedContent,
    normalize_code_content,
    normalize_content,
    normalize_list_content,
    normalize_prose_content,
    normalize_table_content,
    normalize_unknown_content,
)
import app.rag.cleaning.normalization as normalization_module
import app.rag.cleaning.table_text as table_text_module
from app.rag.cleaning.table_text import (
    TSV_ESCAPED_V1,
    parse_tsv_escaped_v1,
    serialize_tsv_escaped_v1,
)
from app.schemas.document import DocumentContentType


def assert_idempotent(result: NormalizedContent, content_type: DocumentContentType) -> None:
    second = normalize_content(result.content, content_type=content_type)

    assert second.content == result.content


def test_normalized_content_is_frozen_value_object() -> None:
    result = normalize_prose_content("Hello")

    with pytest.raises(FrozenInstanceError):
        result.content = "mutated"


def test_unicode_nfc_normalization_records_change_only_when_output_changes() -> None:
    result = normalize_prose_content("Cafe\u0301")

    assert result.content == "Café"
    assert result.transformations == (UNICODE_NFC,)
    assert normalize_prose_content(result.content).transformations == ()


def test_vietnamese_unicode_is_preserved_under_nfc() -> None:
    content = "Tiếng Việt"
    expected = unicodedata.normalize("NFC", content)

    result = normalize_prose_content(content)

    assert result.content == expected
    assert "Tiếng Việt" == result.content


def test_line_endings_are_normalized_to_lf() -> None:
    result = normalize_prose_content("Line 1\r\nLine 2\rLine 3")

    assert result.content == "Line 1\nLine 2\nLine 3"
    assert LINE_ENDINGS_NORMALIZED in result.transformations


def test_prose_normalizes_nbsp_and_horizontal_whitespace() -> None:
    result = normalize_prose_content("  A\xa0\t  B   ")

    assert result.content == "A B"
    assert result.transformations == (
        NBSP_NORMALIZED,
        PROSE_WHITESPACE_NORMALIZED,
    )


def test_prose_converts_tabs_before_control_cleanup() -> None:
    result = normalize_prose_content("A\t\tB")

    assert result.content == "A B"
    assert result.transformations == (PROSE_WHITESPACE_NORMALIZED,)
    assert CONTROL_CHARACTERS_REMOVED not in result.transformations
    assert result.warnings == ()


def test_prose_removes_residual_unsafe_controls_after_whitespace_policy() -> None:
    result = normalize_prose_content("A\x00B\x7fC")

    assert result.content == "ABC"
    assert result.transformations == (CONTROL_CHARACTERS_REMOVED,)
    assert result.warnings[0].warning_code == SUSPICIOUS_CONTROL_CHARACTERS_REMOVED
    assert result.warnings[0].extra_metadata == {"removed_count": 2}


def test_prose_preserves_meaningful_newlines_and_collapses_repeated_blank_lines() -> None:
    result = normalize_prose_content("  First line  \n\n\n  Second line  ")

    assert result.content == "First line\n\nSecond line"
    assert result.transformations == (PROSE_WHITESPACE_NORMALIZED,)


def test_short_heading_like_paragraph_is_preserved() -> None:
    result = normalize_content(
        "  FAQ  ",
        content_type=DocumentContentType.paragraph,
        extra_metadata={"block_type": "heading"},
    )

    assert result.content == "FAQ"
    assert result.transformations == (PROSE_WHITESPACE_NORMALIZED,)


def test_list_normalization_uses_prose_like_line_policy_without_merging_items() -> None:
    result = normalize_list_content("  1.\tFirst\xa0item  \n  2.   Second  ")

    assert result.content == "1. First item\n2. Second"
    assert result.transformations == (
        NBSP_NORMALIZED,
        LIST_WHITESPACE_NORMALIZED,
    )


def test_table_text_round_trips_escaped_cell_semantics() -> None:
    rows = [["A\tB", "Line 1\nLine 2", r"C:\Docs"]]

    serialized = serialize_tsv_escaped_v1(rows)

    assert serialized == r"A\tB	Line 1\nLine 2	C:\\Docs"
    assert parse_tsv_escaped_v1(serialized) == rows


def test_table_normalization_preserves_real_delimiters_and_empty_cells() -> None:
    content = "A\t\tC\n\t\t"

    result = normalize_table_content(
        content,
        extra_metadata={"serialization_format": TSV_ESCAPED_V1},
    )

    assert result.content == content
    assert result.transformations == ()


def test_table_normalization_preserves_escaped_tabs_newlines_and_backslashes() -> None:
    content = r"A\tB	Line 1\nLine 2	C:\\Docs"

    result = normalize_table_content(
        content,
        extra_metadata={"serialization_format": TSV_ESCAPED_V1},
    )

    assert result.content == content
    assert result.transformations == ()
    assert parse_tsv_escaped_v1(result.content) == [
        ["A\tB", "Line 1\nLine 2", r"C:\Docs"]
    ]


def test_table_normalization_normalizes_cell_text_without_flattening_table() -> None:
    content = "Cafe\u0301\xa0value\tB"

    result = normalize_table_content(
        content,
        extra_metadata={"serialization_format": TSV_ESCAPED_V1},
    )

    assert result.content == "Café value\tB"
    assert result.transformations == (
        UNICODE_NFC,
        NBSP_NORMALIZED,
        TABLE_CELLS_NORMALIZED,
    )


def test_unknown_table_format_is_preserved_conservatively() -> None:
    content = "  A\xa0\tB\r\nC  "

    result = normalize_table_content(content, extra_metadata={})

    assert result.content == content
    assert result.transformations == ()


def test_code_normalization_preserves_indentation_tabs_spaces_and_nbsp() -> None:
    content = "\tdef f():\r\n    return\xa01"

    result = normalize_code_content(content)

    assert result.content == "\tdef f():\n    return\xa01"
    assert result.transformations == (LINE_ENDINGS_NORMALIZED,)


def test_code_does_not_trim_outer_blank_lines_by_default() -> None:
    content = "\n\n  x = 1\n\n"

    result = normalize_code_content(content)

    assert result.content == content
    assert result.transformations == ()


def test_code_removes_residual_unsafe_controls_but_preserves_tabs() -> None:
    result = normalize_code_content("\tprint('x')\x00")

    assert result.content == "\tprint('x')"
    assert result.transformations == (CONTROL_CHARACTERS_REMOVED,)


def test_unknown_content_uses_conservative_generic_normalization() -> None:
    content = "Cafe\u0301\tA\xa0B\rC\x00"

    result = normalize_unknown_content(content)

    assert result.content == "Café\tA\xa0B\nC"
    assert result.transformations == (
        UNICODE_NFC,
        LINE_ENDINGS_NORMALIZED,
        CONTROL_CHARACTERS_REMOVED,
    )


def test_replacement_character_warning_does_not_rewrite_content() -> None:
    result = normalize_prose_content("Bad � text")

    assert result.content == "Bad � text"
    assert result.transformations == ()
    assert [warning.warning_code for warning in result.warnings] == [
        REPLACEMENT_CHARACTER_DETECTED
    ]


def test_possible_mojibake_is_not_warned_without_reviewed_rule() -> None:
    result = normalize_prose_content("FranÃ§ais")

    assert result.content == "FranÃ§ais"
    assert result.warnings == ()


@pytest.mark.parametrize(
    ("content", "content_type", "extra_metadata", "expected"),
    [
        (
            "  Paragraph\ttext  ",
            DocumentContentType.paragraph,
            {},
            "Paragraph text",
        ),
        (
            "  List\titem  ",
            DocumentContentType.list,
            {"block_type": "list_item"},
            "List item",
        ),
        (
            "A\tB\nC\tD",
            DocumentContentType.table,
            {"serialization_format": TSV_ESCAPED_V1},
            "A\tB\nC\tD",
        ),
        (
            "  x = 1\n\treturn x",
            DocumentContentType.code,
            {},
            "  x = 1\n\treturn x",
        ),
        (
            "Unknown\ttext",
            DocumentContentType.unknown,
            {},
            "Unknown\ttext",
        ),
    ],
)
def test_dispatcher_matches_phase_2_raw_unit_shapes(
    content: str,
    content_type: DocumentContentType,
    extra_metadata: dict[str, object],
    expected: str,
) -> None:
    result = normalize_content(
        content,
        content_type=content_type,
        extra_metadata=extra_metadata,
    )

    assert result.content == expected
    assert_idempotent(result, content_type)


@pytest.mark.parametrize(
    ("content", "content_type", "extra_metadata"),
    [
        ("Cafe\u0301\r\ntext", DocumentContentType.paragraph, {}),
        ("  First\titem  ", DocumentContentType.list, {"block_type": "list_item"}),
        (
            "Cafe\u0301\xa0value\tB",
            DocumentContentType.table,
            {"serialization_format": TSV_ESCAPED_V1},
        ),
        ("\tprint('x')\r", DocumentContentType.code, {}),
        ("Unknown\ttext\r", DocumentContentType.unknown, {}),
    ],
)
def test_normalization_is_deterministic_for_same_input(
    content: str,
    content_type: DocumentContentType,
    extra_metadata: dict[str, object],
) -> None:
    first = normalize_content(
        content,
        content_type=content_type,
        extra_metadata=extra_metadata,
    )
    second = normalize_content(
        content,
        content_type=content_type,
        extra_metadata=extra_metadata,
    )

    assert first == second


def test_normalization_module_does_not_import_parser_or_framework_dependencies() -> None:
    source = inspect.getsource(normalization_module) + inspect.getsource(
        table_text_module
    )
    forbidden_imports = [
        "import fitz",
        "import pymupdf",
        "import docx",
        "import bs4",
        "import httpx",
        "import fastapi",
        "from fitz",
        "from pymupdf",
        "from docx",
        "from bs4",
        "from httpx",
        "from fastapi",
    ]

    for forbidden_import in forbidden_imports:
        assert forbidden_import not in source
