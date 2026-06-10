from datetime import datetime
from hashlib import sha256

import pytest
from pydantic import ValidationError

from app.schemas.document import (
    CleanDocumentUnit,
    DocumentChunk,
    DocumentContentType,
    RawDocumentUnit,
)
from app.schemas.source import SourceType


def content_hash(content: str) -> str:
    return sha256(content.encode("utf-8")).hexdigest()


def raw_unit_payload(content: str = "Leave policy allows 12 paid days.") -> dict[str, object]:
    return {
        "document_id": "doc_001",
        "source_id": "src_001",
        "source_type": SourceType.pdf,
        "source_uri": "storage://sources/src_001/raw.pdf",
        "content": content,
        "page_start": 2,
        "page_end": 3,
        "section": "Leave Policy",
        "heading_path": ["Employee Handbook", "Human Resources", "Leave Policy"],
        "content_type": DocumentContentType.paragraph,
        "extra_metadata": {"parser": "fake"},
        "raw_unit_id": "raw_001",
        "unit_index": 0,
        "extracted_at": datetime(2026, 6, 8, 9, 0),
    }


def clean_unit_payload(
    content: str = "Leave policy allows 12 paid days.",
) -> dict[str, object]:
    payload = raw_unit_payload(content)
    payload.pop("raw_unit_id")
    payload.pop("unit_index")
    payload.pop("extracted_at")
    payload.update(
        {
            "clean_unit_id": "clean_001",
            "raw_unit_id": "raw_001",
            "transformations": ["normalize_whitespace"],
            "original_character_count": len(content) + 4,
            "removed_character_count": 4,
            "cleaned_at": datetime(2026, 6, 8, 9, 5),
        }
    )
    return payload


def chunk_payload(content: str = "Leave policy allows 12 paid days.") -> dict[str, object]:
    payload = raw_unit_payload(content)
    payload.pop("raw_unit_id")
    payload.pop("unit_index")
    payload.pop("extracted_at")
    payload.update(
        {
            "chunk_id": "chunk_001",
            "clean_unit_id": "clean_001",
            "chunk_index": 0,
            "start_char": 0,
            "end_char": len(content),
            "token_count": len(content.split()) + 2,
            "chunker_name": "recursive-character",
            "chunker_version": "0.1.0",
            "created_at": datetime(2026, 6, 8, 9, 10),
        }
    )
    return payload


def test_raw_document_unit_accepts_valid_input_and_serializes_derived_fields() -> None:
    unit = RawDocumentUnit(**raw_unit_payload())
    dumped = unit.model_dump()

    assert unit.raw_unit_id == "raw_001"
    assert unit.unit_index == 0
    assert unit.content_type is DocumentContentType.paragraph
    assert unit.page_start == 2
    assert unit.page_end == 3
    assert unit.heading_path == [
        "Employee Handbook",
        "Human Resources",
        "Leave Policy",
    ]
    assert dumped["character_count"] == len(unit.content)
    assert dumped["word_count"] == len(unit.content.split())
    assert dumped["content_hash"] == content_hash(unit.content)


def test_document_content_preserves_non_blank_whitespace() -> None:
    content = "  Leave policy allows 12 paid days.\n"
    unit = RawDocumentUnit(**raw_unit_payload(content))

    assert unit.content == content
    assert unit.model_dump()["character_count"] == len(content)
    assert unit.model_dump()["content_hash"] == content_hash(content)


@pytest.mark.parametrize("content", ["", "   ", "\n\t"])
def test_raw_document_unit_rejects_blank_content(content: str) -> None:
    with pytest.raises(ValidationError, match="content must not be blank"):
        RawDocumentUnit.model_validate(raw_unit_payload(content))


@pytest.mark.parametrize(
    "derived_field",
    ["character_count", "word_count", "content_hash"],
)
def test_raw_document_unit_rejects_derived_fields_as_input(
    derived_field: str,
) -> None:
    payload = raw_unit_payload()
    payload[derived_field] = "caller-value"

    with pytest.raises(ValidationError):
        RawDocumentUnit.model_validate(payload)


def test_clean_document_unit_accepts_valid_input_and_derives_removed_count() -> None:
    payload = clean_unit_payload()
    payload["removed_character_count"] = None

    unit = CleanDocumentUnit(**payload)

    assert unit.clean_unit_id == "clean_001"
    assert unit.raw_unit_id == "raw_001"
    assert unit.removed_character_count == 4
    assert unit.transformations == ["normalize_whitespace"]


def test_document_chunk_accepts_valid_input() -> None:
    chunk = DocumentChunk(**chunk_payload())

    assert chunk.chunk_id == "chunk_001"
    assert chunk.clean_unit_id == "clean_001"
    assert chunk.chunk_index == 0
    assert chunk.start_char == 0
    assert chunk.end_char == len(chunk.content)
    assert chunk.token_count == len(chunk.content.split()) + 2
    assert chunk.chunker_name == "recursive-character"
    assert chunk.created_at == datetime(2026, 6, 8, 9, 10)
    assert chunk.source_uri == "storage://sources/src_001/raw.pdf"


def test_content_hash_is_derived_separately_per_stage() -> None:
    raw = RawDocumentUnit(**raw_unit_payload("  Raw text with spaces.\n"))
    clean = CleanDocumentUnit(**clean_unit_payload("Raw text with spaces."))
    chunk = DocumentChunk(**chunk_payload("Raw text"))

    assert raw.content_hash == content_hash(raw.content)
    assert clean.content_hash == content_hash(clean.content)
    assert chunk.content_hash == content_hash(chunk.content)
    assert len({raw.content_hash, clean.content_hash, chunk.content_hash}) == 3


@pytest.mark.parametrize(
    "field_name",
    [
        "document_id",
        "source_id",
        "content",
        "raw_unit_id",
        "unit_index",
        "extracted_at",
    ],
)
def test_raw_document_unit_rejects_missing_required_fields(field_name: str) -> None:
    payload = raw_unit_payload()
    payload.pop(field_name)

    with pytest.raises(ValidationError):
        RawDocumentUnit.model_validate(payload)


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("document_id", ""),
        ("source_id", "   "),
        ("raw_unit_id", None),
        ("extracted_at", None),
    ],
)
def test_raw_document_unit_rejects_empty_or_null_required_fields(
    field_name: str,
    field_value: object,
) -> None:
    payload = raw_unit_payload()
    payload[field_name] = field_value

    with pytest.raises(ValidationError):
        RawDocumentUnit.model_validate(payload)


def test_raw_document_unit_rejects_negative_unit_index() -> None:
    payload = raw_unit_payload()
    payload["unit_index"] = -1

    with pytest.raises(ValidationError):
        RawDocumentUnit.model_validate(payload)


def test_raw_document_unit_rejects_unknown_fields() -> None:
    payload = raw_unit_payload()
    payload["unknown_field"] = "nope"

    with pytest.raises(ValidationError):
        RawDocumentUnit.model_validate(payload)


def test_raw_document_unit_accepts_extra_metadata() -> None:
    payload = raw_unit_payload()
    payload["extra_metadata"] = {"parser": "pymupdf", "block_index": 3}

    unit = RawDocumentUnit.model_validate(payload)

    assert unit.extra_metadata == {"parser": "pymupdf", "block_index": 3}


def test_raw_document_unit_rejects_page_end_without_page_start() -> None:
    payload = raw_unit_payload()
    payload["page_start"] = None
    payload["page_end"] = 3

    with pytest.raises(ValidationError, match="page_start is required"):
        RawDocumentUnit.model_validate(payload)


def test_raw_document_unit_rejects_page_start_without_page_end() -> None:
    payload = raw_unit_payload()
    payload["page_start"] = 3
    payload["page_end"] = None

    with pytest.raises(ValidationError, match="page_end is required"):
        RawDocumentUnit.model_validate(payload)


@pytest.mark.parametrize(
    ("page_start", "page_end"),
    [
        (0, 1),
        (-1, 1),
        (1, 0),
        (1, -1),
    ],
)
def test_raw_document_unit_rejects_zero_or_negative_pages(
    page_start: int,
    page_end: int,
) -> None:
    payload = raw_unit_payload()
    payload["page_start"] = page_start
    payload["page_end"] = page_end

    with pytest.raises(ValidationError):
        RawDocumentUnit.model_validate(payload)


def test_raw_document_unit_rejects_page_end_before_page_start() -> None:
    payload = raw_unit_payload()
    payload["page_start"] = 4
    payload["page_end"] = 3

    with pytest.raises(
        ValidationError,
        match="page_end must be greater than or equal to page_start",
    ):
        RawDocumentUnit.model_validate(payload)


def test_raw_document_unit_accepts_missing_page_range() -> None:
    payload = raw_unit_payload()
    payload["page_start"] = None
    payload["page_end"] = None

    unit = RawDocumentUnit.model_validate(payload)

    assert unit.page_start is None
    assert unit.page_end is None


def test_raw_document_unit_accepts_single_page_range() -> None:
    payload = raw_unit_payload()
    payload["page_start"] = 5
    payload["page_end"] = 5

    unit = RawDocumentUnit.model_validate(payload)

    assert unit.page_start == 5
    assert unit.page_end == 5


def test_raw_document_unit_rejects_blank_heading_path_items() -> None:
    payload = raw_unit_payload()
    payload["heading_path"] = ["  Employee Handbook  ", "   "]

    with pytest.raises(ValidationError):
        RawDocumentUnit.model_validate(payload)


def test_default_lists_and_extra_metadata_are_not_shared() -> None:
    first = RawDocumentUnit.model_validate(
        raw_unit_payload("First content for isolation.")
    )
    second = RawDocumentUnit.model_validate(
        raw_unit_payload("Second content for isolation.")
    )

    first.heading_path.append("Mutated")
    first.extra_metadata["mutated"] = True

    assert "Mutated" not in second.heading_path
    assert "mutated" not in second.extra_metadata


def test_clean_document_unit_rejects_original_count_below_cleaned_count() -> None:
    payload = clean_unit_payload()
    payload["original_character_count"] = len(payload["content"]) - 1

    with pytest.raises(
        ValidationError,
        match="original_character_count cannot be less",
    ):
        CleanDocumentUnit.model_validate(payload)


def test_clean_document_unit_rejects_negative_original_count() -> None:
    payload = clean_unit_payload()
    payload["original_character_count"] = -1

    with pytest.raises(ValidationError):
        CleanDocumentUnit.model_validate(payload)


def test_clean_document_unit_rejects_inconsistent_removed_count() -> None:
    payload = clean_unit_payload()
    payload["removed_character_count"] = 1

    with pytest.raises(ValidationError, match="removed_character_count is inconsistent"):
        CleanDocumentUnit.model_validate(payload)


def test_clean_document_unit_rejects_blank_transformations() -> None:
    payload = clean_unit_payload()
    payload["transformations"] = ["normalize_whitespace", ""]

    with pytest.raises(ValidationError):
        CleanDocumentUnit.model_validate(payload)


def test_transformations_default_list_is_not_shared() -> None:
    first = CleanDocumentUnit.model_validate(
        {**clean_unit_payload("First clean content."), "transformations": []}
    )
    second = CleanDocumentUnit.model_validate(
        {**clean_unit_payload("Second clean content."), "transformations": []}
    )

    first.transformations.append("mutated")

    assert second.transformations == []


def test_document_chunk_rejects_negative_chunk_index() -> None:
    payload = chunk_payload()
    payload["chunk_index"] = -1

    with pytest.raises(ValidationError):
        DocumentChunk.model_validate(payload)


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("clean_unit_id", ""),
        ("clean_unit_id", None),
        ("chunker_name", "   "),
        ("chunker_name", None),
        ("created_at", None),
    ],
)
def test_document_chunk_rejects_empty_or_null_chunk_fields(
    field_name: str,
    field_value: object,
) -> None:
    payload = chunk_payload()
    payload[field_name] = field_value

    with pytest.raises(ValidationError):
        DocumentChunk.model_validate(payload)


def test_document_chunk_rejects_end_char_without_start_char() -> None:
    payload = chunk_payload()
    payload["start_char"] = None
    payload["end_char"] = 10

    with pytest.raises(ValidationError, match="start_char is required"):
        DocumentChunk.model_validate(payload)


def test_document_chunk_accepts_missing_offsets() -> None:
    payload = chunk_payload()
    payload["start_char"] = None
    payload["end_char"] = None

    chunk = DocumentChunk.model_validate(payload)

    assert chunk.start_char is None
    assert chunk.end_char is None


@pytest.mark.parametrize(
    ("start_char", "end_char"),
    [
        (10, 10),
        (11, 10),
    ],
)
def test_document_chunk_rejects_invalid_offsets(
    start_char: int,
    end_char: int,
) -> None:
    payload = chunk_payload()
    payload["start_char"] = start_char
    payload["end_char"] = end_char

    with pytest.raises(ValidationError, match="end_char must be greater"):
        DocumentChunk.model_validate(payload)


@pytest.mark.parametrize("token_count", [0, -1])
def test_document_chunk_rejects_zero_or_negative_token_count(
    token_count: int,
) -> None:
    payload = chunk_payload()
    payload["token_count"] = token_count

    with pytest.raises(ValidationError):
        DocumentChunk.model_validate(payload)


def test_document_chunk_accepts_missing_token_count() -> None:
    payload = chunk_payload()
    payload["token_count"] = None

    chunk = DocumentChunk.model_validate(payload)

    assert chunk.token_count is None


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("start_char", -1),
        ("end_char", -1),
    ],
)
def test_document_chunk_rejects_negative_offsets(
    field_name: str,
    field_value: int,
) -> None:
    payload = chunk_payload()
    payload[field_name] = field_value

    with pytest.raises(ValidationError):
        DocumentChunk.model_validate(payload)
