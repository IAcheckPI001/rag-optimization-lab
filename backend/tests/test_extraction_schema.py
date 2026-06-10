from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas.document import DocumentContentType, RawDocumentUnit
from app.schemas.extraction import (
    ExtractionInput,
    ExtractionResult,
    ExtractionStats,
    ExtractionWarning,
    FetchedContent,
)
from app.schemas.source import ProcessingStage, SourceType


def raw_unit_payload(
    *,
    raw_unit_id: str = "raw:doc_001:000000",
    unit_index: int = 0,
    source_id: str = "src_001",
    document_id: str = "doc_001",
    source_type: SourceType = SourceType.pdf,
    content: str = "Extracted content.",
) -> dict[str, object]:
    return {
        "document_id": document_id,
        "source_id": source_id,
        "source_type": source_type,
        "source_uri": "storage://sources/src_001/raw.pdf",
        "content": content,
        "page_start": 1,
        "page_end": 1,
        "section": None,
        "heading_path": [],
        "content_type": DocumentContentType.paragraph,
        "extra_metadata": {"parser": "fake"},
        "raw_unit_id": raw_unit_id,
        "unit_index": unit_index,
        "extracted_at": datetime(2026, 6, 8, 9, 0),
    }


def raw_unit(**overrides: object) -> RawDocumentUnit:
    payload = raw_unit_payload(**overrides)
    return RawDocumentUnit.model_validate(payload)


def extraction_result_payload(
    *,
    units: list[RawDocumentUnit] | None = None,
    warnings: list[ExtractionWarning] | None = None,
    stats: ExtractionStats | None = None,
    source_id: str = "src_001",
    document_id: str = "doc_001",
    source_type: SourceType = SourceType.pdf,
) -> dict[str, object]:
    result_units = units if units is not None else [raw_unit()]
    result_warnings = warnings if warnings is not None else []
    result_stats = stats or ExtractionStats(
        total_units=len(result_units),
        warning_count=len(result_warnings),
    )
    return {
        "source_id": source_id,
        "document_id": document_id,
        "source_type": source_type,
        "extractor_name": "fake-extractor",
        "extractor_version": "0.1.0",
        "units": result_units,
        "warnings": result_warnings,
        "stats": result_stats,
    }


def test_extraction_input_accepts_valid_bytes_and_metadata() -> None:
    input_data = ExtractionInput(
        source_id="src_001",
        document_id="doc_001",
        source_type=SourceType.docx,
        source_uri="storage://sources/src_001/raw.docx",
        original_filename="policy.docx",
        media_type=(
            "application/vnd.openxmlformats-officedocument"
            ".wordprocessingml.document"
        ),
        charset="utf-8",
        content_bytes=b"docx bytes",
        extractor_config={"extract_tables": True},
        extra_metadata={"upload_id": "upload_001"},
    )

    assert input_data.source_id == "src_001"
    assert input_data.source_uri == "storage://sources/src_001/raw.docx"
    assert input_data.extractor_config == {"extract_tables": True}


def test_extraction_input_rejects_empty_content_bytes() -> None:
    with pytest.raises(ValidationError):
        ExtractionInput(
            source_id="src_001",
            document_id="doc_001",
            source_type=SourceType.pdf,
            content_bytes=b"",
        )


def test_extraction_input_rejects_blank_source_uri_when_provided() -> None:
    with pytest.raises(ValidationError):
        ExtractionInput(
            source_id="src_001",
            document_id="doc_001",
            source_type=SourceType.pdf,
            source_uri="   ",
            content_bytes=b"pdf bytes",
        )


def test_extraction_input_hides_content_bytes_from_dump_and_repr() -> None:
    input_data = ExtractionInput(
        source_id="src_001",
        document_id="doc_001",
        source_type=SourceType.pdf,
        content_bytes=b"very large binary payload",
    )

    assert "content_bytes" not in input_data.model_dump()
    assert "content_bytes" not in repr(input_data)
    assert "very large binary payload" not in repr(input_data)


def test_extraction_input_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ExtractionInput.model_validate(
            {
                "source_id": "src_001",
                "document_id": "doc_001",
                "source_type": SourceType.pdf,
                "content_bytes": b"pdf bytes",
                "unknown_field": "nope",
            }
        )


def test_fetched_content_accepts_valid_http_metadata() -> None:
    fetched = FetchedContent(
        original_url="https://example.com/a",
        final_url="https://example.com/b",
        content_bytes=b"<html></html>",
        media_type="text/html",
        charset="utf-8",
        status_code=200,
        redirect_count=1,
        extra_metadata={"elapsed_ms": 12},
    )

    assert fetched.status_code == 200
    assert fetched.redirect_count == 1


def test_fetched_content_rejects_empty_content_bytes() -> None:
    with pytest.raises(ValidationError):
        FetchedContent(
            original_url="https://example.com",
            final_url="https://example.com",
            content_bytes=b"",
            status_code=200,
        )


def test_fetched_content_requires_status_code() -> None:
    with pytest.raises(ValidationError):
        FetchedContent.model_validate(
            {
                "original_url": "https://example.com",
                "final_url": "https://example.com",
                "content_bytes": b"<html></html>",
            }
        )


@pytest.mark.parametrize("status_code", [99, 600])
def test_fetched_content_rejects_status_codes_outside_http_range(
    status_code: int,
) -> None:
    with pytest.raises(ValidationError):
        FetchedContent(
            original_url="https://example.com",
            final_url="https://example.com",
            content_bytes=b"<html></html>",
            status_code=status_code,
        )


def test_fetched_content_hides_content_bytes_from_dump_and_repr() -> None:
    fetched = FetchedContent(
        original_url="https://example.com",
        final_url="https://example.com",
        content_bytes=b"very large html payload",
        status_code=200,
    )

    assert "content_bytes" not in fetched.model_dump()
    assert "content_bytes" not in repr(fetched)
    assert "very large html payload" not in repr(fetched)


def test_fetched_content_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        FetchedContent.model_validate(
            {
                "original_url": "https://example.com",
                "final_url": "https://example.com",
                "content_bytes": b"<html></html>",
                "status_code": 200,
                "source_id": "src_001",
            }
        )


def test_extraction_stats_rejects_total_units_less_than_one() -> None:
    with pytest.raises(ValidationError):
        ExtractionStats(total_units=0, warning_count=0)


def test_extraction_stats_rejects_negative_skipped_items() -> None:
    with pytest.raises(ValidationError):
        ExtractionStats(total_units=1, skipped_items=-1, warning_count=0)


def test_extraction_warning_accepts_parsing_and_extracting_stages() -> None:
    parsing = ExtractionWarning(
        warning_code="malformed_structure",
        message="Malformed structure skipped.",
        stage=ProcessingStage.parsing,
        item_index=0,
    )
    extracting = ExtractionWarning(
        warning_code="blank_block",
        message="Blank block skipped.",
        stage=ProcessingStage.extracting,
        unit_index=0,
    )

    assert parsing.stage is ProcessingStage.parsing
    assert extracting.stage is ProcessingStage.extracting


def test_extraction_warning_rejects_unsupported_stage() -> None:
    with pytest.raises(ValidationError, match="stage must be parsing or extracting"):
        ExtractionWarning(
            warning_code="timeout",
            message="Download warning.",
            stage=ProcessingStage.downloading,
        )


@pytest.mark.parametrize("field_name", ["item_index", "unit_index"])
def test_extraction_warning_rejects_negative_positions(field_name: str) -> None:
    payload = {
        "warning_code": "negative_position",
        "message": "Negative position.",
        "stage": ProcessingStage.extracting,
        field_name: -1,
    }

    with pytest.raises(ValidationError):
        ExtractionWarning.model_validate(payload)


def test_extraction_warning_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ExtractionWarning.model_validate(
            {
                "warning_code": "unknown_field",
                "message": "Unknown field.",
                "stage": ProcessingStage.extracting,
                "unknown_field": "nope",
            }
        )


def test_extraction_result_accepts_valid_continuous_units() -> None:
    units = [
        raw_unit(raw_unit_id="raw:doc_001:000000", unit_index=0),
        raw_unit(
            raw_unit_id="raw:doc_001:000001",
            unit_index=1,
            content="Second content.",
        ),
    ]
    result = ExtractionResult.model_validate(
        extraction_result_payload(
            units=units,
            stats=ExtractionStats(total_units=2, warning_count=0),
        )
    )

    assert [unit.unit_index for unit in result.units] == [0, 1]
    assert result.stats.total_units == 2


def test_extraction_result_rejects_empty_units() -> None:
    with pytest.raises(ValidationError):
        ExtractionResult.model_validate(
            extraction_result_payload(
                units=[],
                stats=ExtractionStats(total_units=1, warning_count=0),
            )
        )


def test_extraction_result_rejects_duplicate_raw_unit_ids() -> None:
    units = [
        raw_unit(raw_unit_id="raw:doc_001:000000", unit_index=0),
        raw_unit(raw_unit_id="raw:doc_001:000000", unit_index=1),
    ]

    with pytest.raises(ValidationError, match="raw_unit_id values must be unique"):
        ExtractionResult.model_validate(
            extraction_result_payload(
                units=units,
                stats=ExtractionStats(total_units=2, warning_count=0),
            )
        )


def test_extraction_result_rejects_duplicate_unit_indexes() -> None:
    units = [
        raw_unit(raw_unit_id="raw:doc_001:000000", unit_index=0),
        raw_unit(raw_unit_id="raw:doc_001:000001", unit_index=0),
    ]

    with pytest.raises(ValidationError, match="unit_index values must be unique"):
        ExtractionResult.model_validate(
            extraction_result_payload(
                units=units,
                stats=ExtractionStats(total_units=2, warning_count=0),
            )
        )


def test_extraction_result_rejects_non_continuous_unit_indexes() -> None:
    units = [
        raw_unit(raw_unit_id="raw:doc_001:000000", unit_index=0),
        raw_unit(raw_unit_id="raw:doc_001:000002", unit_index=2),
    ]

    with pytest.raises(ValidationError, match="continuous and ordered"):
        ExtractionResult.model_validate(
            extraction_result_payload(
                units=units,
                stats=ExtractionStats(total_units=2, warning_count=0),
            )
        )


def test_extraction_result_rejects_list_order_that_does_not_match_unit_index() -> None:
    units = [
        raw_unit(raw_unit_id="raw:doc_001:000001", unit_index=1),
        raw_unit(raw_unit_id="raw:doc_001:000000", unit_index=0),
    ]

    with pytest.raises(ValidationError, match="continuous and ordered"):
        ExtractionResult.model_validate(
            extraction_result_payload(
                units=units,
                stats=ExtractionStats(total_units=2, warning_count=0),
            )
        )


@pytest.mark.parametrize(
    ("field_name", "field_value", "error_message"),
    [
        ("source_id", "src_other", "unit source_id must match"),
        ("document_id", "doc_other", "unit document_id must match"),
        ("source_type", SourceType.docx, "unit source_type must match"),
    ],
)
def test_extraction_result_rejects_unit_lineage_mismatch(
    field_name: str,
    field_value: object,
    error_message: str,
) -> None:
    unit_overrides = {field_name: field_value}
    unit = raw_unit(**unit_overrides)

    with pytest.raises(ValidationError, match=error_message):
        ExtractionResult.model_validate(extraction_result_payload(units=[unit]))


def test_extraction_result_rejects_stats_total_units_mismatch() -> None:
    with pytest.raises(ValidationError, match="stats.total_units must match"):
        ExtractionResult.model_validate(
            extraction_result_payload(
                stats=ExtractionStats(total_units=2, warning_count=0)
            )
        )


def test_extraction_result_rejects_stats_warning_count_mismatch() -> None:
    warning = ExtractionWarning(
        warning_code="blank_block",
        message="Blank block skipped.",
        stage=ProcessingStage.extracting,
    )

    with pytest.raises(ValidationError, match="stats.warning_count must match"):
        ExtractionResult.model_validate(
            extraction_result_payload(
                warnings=[warning],
                stats=ExtractionStats(total_units=1, warning_count=0),
            )
        )


def test_extraction_result_rejects_unknown_fields() -> None:
    payload = extraction_result_payload()
    payload["unknown_field"] = "nope"

    with pytest.raises(ValidationError):
        ExtractionResult.model_validate(payload)


def test_default_dict_and_list_fields_are_not_shared() -> None:
    first_input = ExtractionInput(
        source_id="src_001",
        document_id="doc_001",
        source_type=SourceType.pdf,
        content_bytes=b"pdf bytes",
    )
    second_input = ExtractionInput(
        source_id="src_002",
        document_id="doc_002",
        source_type=SourceType.pdf,
        content_bytes=b"pdf bytes",
    )
    first_input.extractor_config["mutated"] = True
    first_input.extra_metadata["mutated"] = True

    first_result = ExtractionResult.model_validate(extraction_result_payload())
    second_result = ExtractionResult.model_validate(extraction_result_payload())
    first_result.warnings.append(
        ExtractionWarning(
            warning_code="blank_block",
            message="Blank block skipped.",
            stage=ProcessingStage.extracting,
        )
    )

    assert first_input.extractor_config == {"mutated": True}
    assert first_input.extra_metadata == {"mutated": True}
    assert second_input.extractor_config == {}
    assert second_input.extra_metadata == {}
    assert len(first_result.warnings) == 1
    assert second_result.warnings == []
