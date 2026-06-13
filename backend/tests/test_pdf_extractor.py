import importlib.metadata
import base64

import pytest

import pymupdf

from app.providers.extraction.pdf_extractor import PdfExtractor
from app.providers.extraction.errors import (
    ExtractionNoContentError,
    ExtractionParsingError,
    ExtractionSourceTypeMismatchError,
)
from app.schemas.document import DocumentContentType
from app.schemas.extraction import ExtractionInput, ExtractionResult
from app.schemas.source import SourceType


def pdf_bytes(pages: list[list[tuple[str, float, float]]]) -> bytes:
    document = pymupdf.open()
    try:
        for page_texts in pages:
            page = document.new_page()
            for text, x, y in page_texts:
                page.insert_text((x, y), text)
        return document.tobytes()
    finally:
        document.close()


def blank_pdf_bytes(page_count: int = 1) -> bytes:
    document = pymupdf.open()
    try:
        for _ in range(page_count):
            document.new_page()
        return document.tobytes()
    finally:
        document.close()


def encrypted_pdf_bytes() -> bytes:
    document = pymupdf.open()
    try:
        page = document.new_page()
        page.insert_text((72, 72), "Secret content")
        return document.tobytes(
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            owner_pw="owner-password",
            user_pw="user-password",
        )
    finally:
        document.close()


def image_only_pdf_bytes() -> bytes:
    image_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8"
        "AAwMCAO+/p9sAAAAASUVORK5CYII="
    )
    document = pymupdf.open()
    try:
        page = document.new_page()
        page.insert_image(pymupdf.Rect(72, 72, 100, 100), stream=image_bytes)
        return document.tobytes()
    finally:
        document.close()


def extraction_input(content_bytes: bytes, source_type: SourceType = SourceType.pdf):
    return ExtractionInput(
        source_id="src_001",
        document_id="doc_001",
        source_type=source_type,
        source_uri="storage://sources/src_001/raw.pdf",
        original_filename="policy.pdf",
        media_type="application/pdf",
        content_bytes=content_bytes,
    )


def extract(content_bytes: bytes) -> ExtractionResult:
    return PdfExtractor(extractor_version="test-version").extract(
        extraction_input(content_bytes)
    )


def test_pymupdf_import_and_package_version_resolve() -> None:
    assert pymupdf.open is not None
    assert importlib.metadata.version("PyMuPDF") != "unknown"


def test_pdf_extractor_extracts_single_text_block() -> None:
    result = extract(pdf_bytes([[("Leave policy allows 12 paid days.", 72, 72)]]))
    unit = result.units[0]

    assert result.extractor_name == "pymupdf"
    assert result.extractor_version == "test-version"
    assert unit.content.strip() == "Leave policy allows 12 paid days."
    assert unit.content_type is DocumentContentType.paragraph
    assert unit.unit_index == 0
    assert unit.raw_unit_id == "raw:doc_001:000000"
    assert unit.page_start == 1
    assert unit.page_end == 1
    assert unit.section is None
    assert unit.heading_path == []
    assert unit.source_uri == "storage://sources/src_001/raw.pdf"
    assert unit.extra_metadata["parser"] == "pymupdf"
    assert unit.extra_metadata["parser_version"] == "test-version"
    assert unit.extra_metadata["block_type"] == "text"
    assert unit.extra_metadata["page_index"] == 0
    assert unit.extra_metadata["page_number"] == 1
    assert unit.extra_metadata["page_block_index"] == 0
    assert len(unit.extra_metadata["bbox"]) == 4
    assert all(isinstance(value, float) for value in unit.extra_metadata["bbox"])
    assert unit.character_count == len(unit.content)
    assert result.stats.total_units == 1
    assert result.stats.skipped_items == 0
    assert result.stats.extra_metadata["page_count"] == 1
    assert result.stats.extra_metadata["blank_page_count"] == 0
    assert result.stats.extra_metadata["pages_with_text_count"] == 1
    assert (
        result.stats.extra_metadata["pages_with_text_count"]
        + result.stats.extra_metadata["blank_page_count"]
        == result.stats.extra_metadata["page_count"]
    )
    assert result.stats.total_units == len(result.units)
    assert result.stats.warning_count == len(result.warnings)
    assert (
        result.stats.extra_metadata["total_observed_blocks"]
        == result.stats.total_units + result.stats.skipped_items
    )
    assert result.stats.extra_metadata["text_block_count"] == 1


def test_pdf_extractor_preserves_page_and_block_order() -> None:
    result = extract(
        pdf_bytes(
            [
                [("Second block on page one", 72, 180), ("First block on page one", 72, 72)],
                [("Only block on page two", 72, 72)],
            ]
        )
    )

    assert [unit.content.strip() for unit in result.units] == [
        "First block on page one",
        "Second block on page one",
        "Only block on page two",
    ]
    assert [unit.unit_index for unit in result.units] == [0, 1, 2]
    assert [unit.raw_unit_id for unit in result.units] == [
        "raw:doc_001:000000",
        "raw:doc_001:000001",
        "raw:doc_001:000002",
    ]
    assert [unit.page_start for unit in result.units] == [1, 1, 2]
    assert [unit.page_end for unit in result.units] == [1, 1, 2]
    assert [unit.extra_metadata["page_block_index"] for unit in result.units] == [
        0,
        1,
        0,
    ]
    assert result.stats.extra_metadata["page_count"] == 2
    assert result.stats.extra_metadata["pages_with_text_count"] == 2
    assert result.stats.extra_metadata["blank_page_count"] == 0


def test_pdf_extractor_tracks_blank_pages_without_emitting_blank_units() -> None:
    result = extract(pdf_bytes([[], [("Text after blank page", 72, 72)]]))

    assert len(result.units) == 1
    assert result.units[0].content.strip() == "Text after blank page"
    assert result.units[0].page_start == 2
    assert result.stats.skipped_items == 0
    assert result.stats.extra_metadata["page_count"] == 2
    assert result.stats.extra_metadata["blank_page_count"] == 1
    assert result.stats.extra_metadata["pages_with_text_count"] == 1
    assert (
        result.stats.extra_metadata["pages_with_text_count"]
        + result.stats.extra_metadata["blank_page_count"]
        == result.stats.extra_metadata["page_count"]
    )
    assert result.stats.total_units == len(result.units)
    assert result.stats.warning_count == len(result.warnings)
    assert (
        result.stats.extra_metadata["total_observed_blocks"]
        == result.stats.total_units + result.stats.skipped_items
    )
    assert result.stats.extra_metadata["total_observed_blocks"] == 1
    assert result.stats.extra_metadata["text_block_count"] == 1


@pytest.mark.parametrize(
    "bbox_value",
    [
        "not-a-number",
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_pdf_extractor_skips_malformed_bbox_with_warning(
    monkeypatch: pytest.MonkeyPatch,
    bbox_value: object,
) -> None:
    original_get_text = pymupdf.Page.get_text

    def fake_get_text(self, *args, **kwargs):
        blocks = original_get_text(self, *args, **kwargs)
        if not blocks:
            return blocks
        malformed = list(blocks[0])
        malformed[0] = bbox_value
        return [tuple(malformed), *blocks[1:]]

    monkeypatch.setattr(pymupdf.Page, "get_text", fake_get_text)

    result = extract(
        pdf_bytes(
            [
                [("Malformed bbox block", 72, 72), ("Valid following block", 72, 180)]
            ]
        )
    )

    assert [unit.content.strip() for unit in result.units] == ["Valid following block"]
    assert result.units[0].unit_index == 0
    assert result.units[0].raw_unit_id == "raw:doc_001:000000"
    assert result.units[0].extra_metadata["page_block_index"] == 1
    assert result.stats.skipped_items == 1
    assert result.stats.warning_count == 1
    assert len(result.warnings) == 1
    warning = result.warnings[0]
    assert warning.warning_code == "malformed_pdf_block"
    assert warning.item_index == 0
    assert warning.extra_metadata["page_index"] == 0
    assert warning.extra_metadata["page_number"] == 1
    assert warning.extra_metadata["page_block_index"] == 0
    assert "content_bytes" not in warning.extra_metadata
    assert "Malformed bbox block" not in str(warning.extra_metadata)
    assert (
        result.stats.extra_metadata["total_observed_blocks"]
        == result.stats.total_units + result.stats.skipped_items
    )


def test_pdf_extractor_is_deterministic_except_extracted_at() -> None:
    content = pdf_bytes(
        [
            [("Alpha", 72, 72), ("Beta", 72, 180)],
            [("Gamma", 72, 72)],
        ]
    )

    first = extract(content)
    second = extract(content)

    comparable_first = [
        (
            unit.content,
            unit.content_type,
            unit.unit_index,
            unit.raw_unit_id,
            unit.page_start,
            unit.page_end,
            unit.section,
            unit.heading_path,
            unit.extra_metadata,
        )
        for unit in first.units
    ]
    comparable_second = [
        (
            unit.content,
            unit.content_type,
            unit.unit_index,
            unit.raw_unit_id,
            unit.page_start,
            unit.page_end,
            unit.section,
            unit.heading_path,
            unit.extra_metadata,
        )
        for unit in second.units
    ]

    assert comparable_first == comparable_second
    assert len({unit.extracted_at for unit in first.units}) == 1


def test_pdf_extractor_rejects_source_type_mismatch() -> None:
    with pytest.raises(ExtractionSourceTypeMismatchError) as exc_info:
        PdfExtractor(extractor_version="test-version").extract(
            extraction_input(
                pdf_bytes([[("DOCX mismatch", 72, 72)]]), SourceType.docx
            )
        )

    assert exc_info.value.error_code == "extraction_source_type_mismatch"
    assert "content_bytes" not in exc_info.value.details


@pytest.mark.parametrize("content_bytes", [b"not a pdf", b"%PDF-1.7\nbroken"])
def test_pdf_extractor_raises_parsing_error_for_invalid_pdf(
    content_bytes: bytes,
) -> None:
    with pytest.raises(ExtractionParsingError) as exc_info:
        PdfExtractor(extractor_version="test-version").extract(
            extraction_input(content_bytes)
        )

    assert exc_info.value.error_code == "extraction_parsing_failed"
    assert "content_bytes" not in exc_info.value.details


def test_pdf_extractor_raises_parsing_error_for_password_protected_pdf() -> None:
    with pytest.raises(ExtractionParsingError) as exc_info:
        PdfExtractor(extractor_version="test-version").extract(
            extraction_input(encrypted_pdf_bytes())
        )

    assert exc_info.value.error_code == "extraction_parsing_failed"
    assert "content_bytes" not in exc_info.value.details


def test_pdf_extractor_raises_no_content_for_blank_pdf() -> None:
    with pytest.raises(ExtractionNoContentError) as exc_info:
        PdfExtractor(extractor_version="test-version").extract(
            extraction_input(blank_pdf_bytes())
        )

    assert exc_info.value.error_code == "extraction_no_content"
    assert exc_info.value.details["page_count"] == 1
    assert exc_info.value.details["blank_page_count"] == 1
    assert "content_bytes" not in exc_info.value.details


def test_pdf_extractor_raises_no_content_for_image_only_pdf() -> None:
    with pytest.raises(ExtractionNoContentError) as exc_info:
        PdfExtractor(extractor_version="test-version").extract(
            extraction_input(image_only_pdf_bytes())
        )

    assert exc_info.value.error_code == "extraction_no_content"
    assert exc_info.value.details["page_count"] == 1
    assert exc_info.value.details["blank_page_count"] == 1
    assert exc_info.value.details["text_block_count"] == 0
    assert "content_bytes" not in exc_info.value.details
