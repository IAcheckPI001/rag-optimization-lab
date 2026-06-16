from datetime import datetime, timezone

from app.rag.cleaning.source_filters import (
    HTML_READING_TIME,
    HTML_UI_NOISE,
    PDF_PAGE_NUMBER,
    POSSIBLE_PAGE_NUMBER,
)
from app.rag.cleaning.rule_based_cleaner import RuleBasedDocumentCleaner
from app.schemas.cleaning import CleaningInput
from app.schemas.document import DocumentContentType, RawDocumentUnit
from app.schemas.source import SourceType


FIXED_TIME = datetime(2026, 6, 13, tzinfo=timezone.utc)


def raw_unit(
    unit_index: int,
    content: str,
    *,
    source_type: SourceType = SourceType.pdf,
    content_type: DocumentContentType = DocumentContentType.paragraph,
    page_start: int | None = None,
    page_end: int | None = None,
    extra_metadata: dict[str, object] | None = None,
) -> RawDocumentUnit:
    document_id = "document-001"
    return RawDocumentUnit.model_validate(
        {
            "document_id": document_id,
            "source_id": "source-001",
            "source_type": source_type,
            "source_uri": "https://example.test/article"
            if source_type is SourceType.url
            else "storage://sources/source-001/raw",
            "content": content,
            "page_start": page_start,
            "page_end": page_end,
            "section": None,
            "heading_path": [],
            "content_type": content_type,
            "extra_metadata": extra_metadata or {},
            "raw_unit_id": f"raw:{document_id}:{unit_index:06d}",
            "unit_index": unit_index,
            "extracted_at": datetime(2026, 6, 12, tzinfo=timezone.utc),
        }
    )


def cleaning_input(
    units: list[RawDocumentUnit],
    *,
    source_type: SourceType,
) -> CleaningInput:
    return CleaningInput.model_validate(
        {
            "source_id": "source-001",
            "document_id": "document-001",
            "source_type": source_type,
            "units": units,
        }
    )


def clean(units: list[RawDocumentUnit], *, source_type: SourceType):
    return RuleBasedDocumentCleaner(clock=lambda: FIXED_TIME).clean(
        cleaning_input(units, source_type=source_type)
    )


def html_unit(
    unit_index: int,
    content: str,
    *,
    block_type: str = "container_text",
    content_type: DocumentContentType = DocumentContentType.paragraph,
) -> RawDocumentUnit:
    return raw_unit(
        unit_index,
        content,
        source_type=SourceType.url,
        content_type=content_type,
        extra_metadata={
            "block_type": block_type,
            "block_index": unit_index,
            "html_tag": "div",
            "nearest_semantic_container": "main",
        },
    )


def pdf_unit(
    unit_index: int,
    content: str,
    *,
    page_number: int = 2,
    page_start: int = 2,
    page_end: int = 2,
    extra_metadata: dict[str, object] | None = None,
) -> RawDocumentUnit:
    metadata = {
        "block_type": "text",
        "block_index": unit_index,
        "page_index": page_number - 1,
        "page_number": page_number,
        "page_block_index": unit_index,
        "document_block_index": unit_index,
    }
    if extra_metadata:
        metadata.update(extra_metadata)

    return raw_unit(
        unit_index,
        content,
        source_type=SourceType.pdf,
        page_start=page_start,
        page_end=page_end,
        extra_metadata=metadata,
    )


def test_html_ui_noise_drops_only_url_container_text() -> None:
    result = clean(
        [
            html_unit(0, "Link Copied!"),
            html_unit(1, "Article body", block_type="paragraph"),
        ],
        source_type=SourceType.url,
    )

    assert [unit.content for unit in result.units] == ["Article body"]
    assert [unit.clean_unit_index for unit in result.units] == [0]
    assert result.units[0].clean_unit_id == "clean:document-001:000001"
    assert result.dropped_units[0].reason_code == HTML_UI_NOISE
    assert result.dropped_units[0].original_content_hash
    assert result.dropped_units[0].extra_metadata == {
        "block_type": "container_text",
        "block_index": 0,
        "html_tag": "div",
        "nearest_semantic_container": "main",
    }
    assert result.stats.extra_metadata["html_ui_noise_dropped_count"] == 1


def test_html_ui_noise_text_is_preserved_for_non_url_sources() -> None:
    for source_type in [SourceType.docx, SourceType.pdf]:
        result = clean(
            [
                raw_unit(
                    0,
                    "Share",
                    source_type=source_type,
                    extra_metadata={"block_type": "container_text"},
                )
            ],
            source_type=source_type,
        )

        assert [unit.content for unit in result.units] == ["Share"]
        assert result.dropped_units == []


def test_html_ui_noise_text_is_preserved_for_normal_paragraph_provenance() -> None:
    result = clean(
        [html_unit(0, "Share", block_type="paragraph")],
        source_type=SourceType.url,
    )

    assert [unit.content for unit in result.units] == ["Share"]
    assert result.dropped_units == []


def test_html_reading_time_drops_only_full_contextual_label() -> None:
    result = clean(
        [
            html_unit(0, "7 min read"),
            html_unit(1, "This process takes 7 min to read the file."),
        ],
        source_type=SourceType.url,
    )

    assert [unit.content for unit in result.units] == [
        "This process takes 7 min to read the file."
    ]
    assert result.dropped_units[0].reason_code == HTML_READING_TIME
    assert result.stats.extra_metadata["html_reading_time_dropped_count"] == 1


def test_html_document_title_and_heading_duplicates_are_preserved() -> None:
    result = clean(
        [
            html_unit(0, "Investigation", block_type="document_title"),
            html_unit(1, "Investigation", block_type="heading"),
        ],
        source_type=SourceType.url,
    )

    assert [unit.content for unit in result.units] == [
        "Investigation",
        "Investigation",
    ]
    assert result.dropped_units == []


def test_pdf_page_number_candidate_with_bbox_but_missing_dimensions_warns() -> None:
    result = clean(
        [pdf_unit(0, "2", extra_metadata={"bbox": [290.0, 760.0, 302.0, 772.0]})],
        source_type=SourceType.pdf,
    )

    assert [unit.content for unit in result.units] == ["2"]
    assert result.dropped_units == []
    assert len(result.warnings) == 1
    warning = result.warnings[0]
    assert warning.warning_code == POSSIBLE_PAGE_NUMBER
    assert warning.clean_unit_index == 0
    assert warning.extra_metadata == {
        "page_number": 2,
        "page_start": 2,
        "page_end": 2,
        "has_bbox": True,
        "has_page_dimensions": False,
        "geometry_status": "missing_page_dimensions",
        "edge_band": "unknown",
    }
    assert result.stats.extra_metadata["source_filter_warning_count"] == 1
    assert result.stats.extra_metadata["possible_page_number_warning_count"] == 1


def test_pdf_page_index_is_never_used_as_page_number_text() -> None:
    result = clean(
        [
            pdf_unit(
                0,
                "1",
                page_number=2,
                page_start=2,
                page_end=2,
                extra_metadata={
                    "page_index": 1,
                    "bbox": [290.0, 760.0, 302.0, 772.0],
                },
            )
        ],
        source_type=SourceType.pdf,
    )

    assert [unit.content for unit in result.units] == ["1"]
    assert result.warnings == []
    assert result.dropped_units == []


def test_pdf_inconsistent_page_provenance_preserves_content() -> None:
    result = clean(
        [
            pdf_unit(
                0,
                "2",
                page_number=3,
                page_start=2,
                page_end=2,
                extra_metadata={"bbox": [290.0, 760.0, 302.0, 772.0]},
            )
        ],
        source_type=SourceType.pdf,
    )

    assert [unit.content for unit in result.units] == ["2"]
    assert result.warnings == []
    assert result.dropped_units == []


def test_pdf_non_exact_page_number_variants_are_preserved() -> None:
    result = clean(
        [
            pdf_unit(0, "Page 2", extra_metadata={"bbox": [290.0, 760.0, 302.0, 772.0]}),
            pdf_unit(
                1,
                "2026",
                page_number=2,
                page_start=2,
                page_end=2,
                extra_metadata={"bbox": [290.0, 720.0, 330.0, 735.0]},
            ),
        ],
        source_type=SourceType.pdf,
    )

    assert [unit.content for unit in result.units] == ["Page 2", "2026"]
    assert result.warnings == []
    assert result.dropped_units == []


def test_pdf_footer_page_number_with_reliable_geometry_is_dropped() -> None:
    result = clean(
        [
            pdf_unit(
                0,
                "2",
                extra_metadata={
                    "bbox": [290.0, 760.0, 302.0, 772.0],
                    "page_width": 600.0,
                    "page_height": 800.0,
                },
            ),
            pdf_unit(1, "Body text on page 2."),
        ],
        source_type=SourceType.pdf,
    )

    assert [unit.content for unit in result.units] == ["Body text on page 2."]
    assert [unit.clean_unit_index for unit in result.units] == [0]
    assert result.units[0].clean_unit_id == "clean:document-001:000001"
    assert result.dropped_units[0].reason_code == PDF_PAGE_NUMBER
    assert result.dropped_units[0].extra_metadata["bbox"] == [
        290.0,
        760.0,
        302.0,
        772.0,
    ]
    assert result.dropped_units[0].extra_metadata["page_width"] == 600.0
    assert result.stats.extra_metadata["pdf_page_number_dropped_count"] == 1


def test_pdf_header_page_number_with_reliable_geometry_is_preserved_and_warned() -> None:
    result = clean(
        [
            pdf_unit(
                0,
                "2",
                extra_metadata={
                    "bbox": [290.0, 18.0, 302.0, 30.0],
                    "page_width": 600.0,
                    "page_height": 800.0,
                },
            )
        ],
        source_type=SourceType.pdf,
    )

    assert [unit.content for unit in result.units] == ["2"]
    assert result.dropped_units == []
    assert result.warnings[0].warning_code == POSSIBLE_PAGE_NUMBER
    assert result.warnings[0].extra_metadata["edge_band"] == "header"
    assert result.warnings[0].extra_metadata["geometry_status"] == "valid_header_band"


def test_pdf_middle_page_number_like_content_is_preserved_silently() -> None:
    result = clean(
        [
            pdf_unit(
                0,
                "2",
                extra_metadata={
                    "bbox": [290.0, 360.0, 302.0, 372.0],
                    "page_width": 600.0,
                    "page_height": 800.0,
                },
            )
        ],
        source_type=SourceType.pdf,
    )

    assert [unit.content for unit in result.units] == ["2"]
    assert result.warnings == []
    assert result.dropped_units == []


def test_pdf_invalid_bbox_preserves_content_and_does_not_fail() -> None:
    result = clean(
        [
            pdf_unit(
                0,
                "2",
                extra_metadata={
                    "bbox": ["bad", 760.0, 302.0, 772.0],
                    "page_width": 600.0,
                    "page_height": 800.0,
                },
            )
        ],
        source_type=SourceType.pdf,
    )

    assert [unit.content for unit in result.units] == ["2"]
    assert result.warnings == []
    assert result.dropped_units == []
