from datetime import datetime, timezone
from hashlib import sha256

import pytest
from pydantic import ValidationError

from app.schemas.cleaning import (
    CleaningInput,
    CleaningResult,
    CleaningStats,
    CleaningWarning,
    DroppedUnit,
)
from app.schemas.document import CleanDocumentUnit, DocumentContentType, RawDocumentUnit
from app.schemas.source import ProcessingStage, SourceType


CLEANED_AT = datetime(2026, 6, 13, tzinfo=timezone.utc)


def raw_unit_payload(unit_index: int = 0, content: str | None = None) -> dict[str, object]:
    unit_content = content or f"Raw content {unit_index}"
    return {
        "document_id": "document-001",
        "source_id": "source-001",
        "source_type": SourceType.pdf,
        "source_uri": "storage://sources/source-001/raw.pdf",
        "content": unit_content,
        "page_start": unit_index + 1,
        "page_end": unit_index + 1,
        "section": "Policy",
        "heading_path": ["Policy"],
        "content_type": DocumentContentType.paragraph,
        "extra_metadata": {"block_index": unit_index},
        "raw_unit_id": f"raw:document-001:{unit_index:06d}",
        "unit_index": unit_index,
        "extracted_at": datetime(2026, 6, 12, tzinfo=timezone.utc),
    }


def raw_unit(unit_index: int = 0, content: str | None = None) -> RawDocumentUnit:
    return RawDocumentUnit.model_validate(raw_unit_payload(unit_index, content))


def clean_unit_payload(
    clean_unit_index: int = 0,
    raw_unit_index: int = 0,
    *,
    raw_unit_id: str | None = None,
    clean_unit_id: str | None = None,
    cleaned_at: datetime = CLEANED_AT,
) -> dict[str, object]:
    return {
        "document_id": "document-001",
        "source_id": "source-001",
        "source_type": SourceType.pdf,
        "source_uri": "storage://sources/source-001/raw.pdf",
        "content": f"Clean content {raw_unit_index}",
        "page_start": raw_unit_index + 1,
        "page_end": raw_unit_index + 1,
        "section": "Policy",
        "heading_path": ["Policy"],
        "content_type": DocumentContentType.paragraph,
        "extra_metadata": {"normalizer": "rule-based"},
        "clean_unit_id": clean_unit_id
        or f"clean:document-001:{raw_unit_index:06d}",
        "clean_unit_index": clean_unit_index,
        "raw_unit_id": raw_unit_id or f"raw:document-001:{raw_unit_index:06d}",
        "transformations": ["unicode_nfc", "prose_whitespace_normalized"],
        "cleaned_at": cleaned_at,
    }


def clean_unit(
    clean_unit_index: int = 0,
    raw_unit_index: int = 0,
    **overrides: object,
) -> CleanDocumentUnit:
    payload = clean_unit_payload(clean_unit_index, raw_unit_index)
    payload.update(overrides)
    return CleanDocumentUnit.model_validate(payload)


def dropped_unit_payload(unit_index: int = 1) -> dict[str, object]:
    content = f"Dropped raw content {unit_index}"
    return {
        "raw_unit_id": f"raw:document-001:{unit_index:06d}",
        "unit_index": unit_index,
        "reason_code": "empty_after_normalization",
        "message": "Unit became empty after normalization.",
        "original_content_hash": sha256(content.encode("utf-8")).hexdigest(),
        "source_type": SourceType.pdf,
        "page_start": unit_index + 1,
        "page_end": unit_index + 1,
        "section": "Policy",
        "content_type": DocumentContentType.paragraph,
        "extra_metadata": {"raw_character_count": len(content)},
    }


def warning_payload() -> dict[str, object]:
    return {
        "warning_code": "possible_page_number",
        "message": "Possible PDF page number preserved.",
        "stage": ProcessingStage.cleaning,
        "raw_unit_id": "raw:document-001:000001",
        "clean_unit_index": None,
        "extra_metadata": {"reason": "missing_page_dimensions"},
    }


def stats_payload(
    *,
    total_input_units: int = 2,
    total_output_units: int = 1,
    dropped_unit_count: int = 1,
    modified_unit_count: int = 1,
    unchanged_unit_count: int = 0,
    warning_count: int = 1,
) -> dict[str, object]:
    return {
        "total_input_units": total_input_units,
        "total_output_units": total_output_units,
        "dropped_unit_count": dropped_unit_count,
        "modified_unit_count": modified_unit_count,
        "unchanged_unit_count": unchanged_unit_count,
        "warning_count": warning_count,
        "characters_before": 42,
        "characters_after": 20,
        "extra_metadata": {"rule_count": 3},
    }


def result_payload() -> dict[str, object]:
    return {
        "source_id": "source-001",
        "document_id": "document-001",
        "source_type": SourceType.pdf,
        "cleaner_name": "rule-based",
        "cleaner_version": "0.1.0",
        "units": [clean_unit(0, 0)],
        "dropped_units": [DroppedUnit.model_validate(dropped_unit_payload(1))],
        "warnings": [CleaningWarning.model_validate(warning_payload())],
        "stats": CleaningStats.model_validate(stats_payload()),
    }


def test_cleaning_input_accepts_valid_continuous_raw_units() -> None:
    input_data = CleaningInput.model_validate(
        {
            "source_id": "source-001",
            "document_id": "document-001",
            "source_type": SourceType.pdf,
            "units": [raw_unit(0), raw_unit(1)],
            "cleaner_config": {"preserve_headings": True},
            "extra_metadata": {"batch_id": "batch-001"},
        }
    )

    assert [unit.unit_index for unit in input_data.units] == [0, 1]
    assert input_data.cleaner_config == {"preserve_headings": True}


def test_cleaning_input_rejects_empty_units() -> None:
    with pytest.raises(ValidationError):
        CleaningInput.model_validate(
            {
                "source_id": "source-001",
                "document_id": "document-001",
                "source_type": SourceType.pdf,
                "units": [],
            }
        )


def test_cleaning_input_rejects_duplicate_raw_unit_ids() -> None:
    second = raw_unit(1, "Second raw unit")
    second.raw_unit_id = "raw:document-001:000000"

    with pytest.raises(ValidationError, match="raw_unit_id values must be unique"):
        CleaningInput.model_validate(
            {
                "source_id": "source-001",
                "document_id": "document-001",
                "source_type": SourceType.pdf,
                "units": [raw_unit(0), second],
            }
        )


def test_cleaning_input_rejects_duplicate_raw_unit_indexes() -> None:
    second = raw_unit(1, "Second raw unit")
    second.unit_index = 0

    with pytest.raises(ValidationError, match="unit_index values must be unique"):
        CleaningInput.model_validate(
            {
                "source_id": "source-001",
                "document_id": "document-001",
                "source_type": SourceType.pdf,
                "units": [raw_unit(0), second],
            }
        )


def test_cleaning_input_rejects_non_continuous_raw_unit_indexes() -> None:
    with pytest.raises(
        ValidationError,
        match="unit_index values must be continuous and ordered from 0",
    ):
        CleaningInput.model_validate(
            {
                "source_id": "source-001",
                "document_id": "document-001",
                "source_type": SourceType.pdf,
                "units": [raw_unit(0), raw_unit(2)],
            }
        )


def test_cleaning_input_rejects_unit_lineage_mismatch() -> None:
    mismatched = raw_unit(0)
    mismatched.document_id = "other-document"

    with pytest.raises(ValidationError, match="unit document_id must match"):
        CleaningInput.model_validate(
            {
                "source_id": "source-001",
                "document_id": "document-001",
                "source_type": SourceType.pdf,
                "units": [mismatched],
            }
        )


def test_cleaning_warning_accepts_optional_unit_indexes() -> None:
    warning = CleaningWarning.model_validate(warning_payload())

    assert warning.stage is ProcessingStage.cleaning
    assert warning.clean_unit_index is None


def test_cleaning_warning_accepts_emitted_clean_unit_index() -> None:
    payload = warning_payload()
    payload["clean_unit_index"] = 0

    warning = CleaningWarning.model_validate(payload)

    assert warning.clean_unit_index == 0


def test_cleaning_warning_rejects_non_cleaning_stage() -> None:
    payload = warning_payload()
    payload["stage"] = ProcessingStage.extracting

    with pytest.raises(ValidationError, match="stage must be cleaning"):
        CleaningWarning.model_validate(payload)


def test_cleaning_warning_rejects_negative_clean_unit_index() -> None:
    payload = warning_payload()
    payload["clean_unit_index"] = -1

    with pytest.raises(ValidationError):
        CleaningWarning.model_validate(payload)


def test_dropped_unit_accepts_valid_raw_position() -> None:
    dropped = DroppedUnit.model_validate(dropped_unit_payload())

    assert dropped.unit_index == 1
    assert dropped.raw_unit_id == "raw:document-001:000001"


def test_dropped_unit_requires_unit_index() -> None:
    payload = dropped_unit_payload()
    payload.pop("unit_index")

    with pytest.raises(ValidationError):
        DroppedUnit.model_validate(payload)


def test_dropped_unit_rejects_negative_unit_index() -> None:
    payload = dropped_unit_payload()
    payload["unit_index"] = -1

    with pytest.raises(ValidationError):
        DroppedUnit.model_validate(payload)


def test_dropped_unit_rejects_invalid_page_range() -> None:
    payload = dropped_unit_payload()
    payload["page_start"] = 4
    payload["page_end"] = 3

    with pytest.raises(ValidationError, match="page_end must be greater"):
        DroppedUnit.model_validate(payload)


def test_cleaning_stats_rejects_invalid_counts() -> None:
    payload = stats_payload()
    payload["total_input_units"] = 0

    with pytest.raises(ValidationError):
        CleaningStats.model_validate(payload)


def test_cleaning_result_accepts_valid_contract() -> None:
    result = CleaningResult.model_validate(result_payload())

    assert result.units[0].clean_unit_index == 0
    assert result.dropped_units[0].unit_index == 1
    assert result.stats.total_input_units == 2


def test_cleaning_result_rejects_duplicate_clean_unit_ids() -> None:
    payload = result_payload()
    payload["units"] = [
        clean_unit(0, 0, clean_unit_id="clean:document-001:000000"),
        clean_unit(1, 2, clean_unit_id="clean:document-001:000000"),
    ]
    payload["stats"] = CleaningStats.model_validate(
        stats_payload(total_input_units=3, total_output_units=2, dropped_unit_count=1)
    )

    with pytest.raises(ValidationError, match="clean_unit_id values must be unique"):
        CleaningResult.model_validate(payload)


def test_cleaning_result_rejects_duplicate_clean_unit_indexes() -> None:
    payload = result_payload()
    payload["units"] = [clean_unit(0, 0), clean_unit(0, 2)]
    payload["stats"] = CleaningStats.model_validate(
        stats_payload(total_input_units=3, total_output_units=2, dropped_unit_count=1)
    )

    with pytest.raises(
        ValidationError,
        match="clean_unit_index values must be unique",
    ):
        CleaningResult.model_validate(payload)


def test_cleaning_result_rejects_non_continuous_clean_unit_indexes() -> None:
    payload = result_payload()
    payload["units"] = [clean_unit(0, 0), clean_unit(2, 2)]
    payload["stats"] = CleaningStats.model_validate(
        stats_payload(total_input_units=3, total_output_units=2, dropped_unit_count=1)
    )

    with pytest.raises(
        ValidationError,
        match="clean_unit_index values must be continuous and ordered from 0",
    ):
        CleaningResult.model_validate(payload)


def test_cleaning_result_rejects_unit_lineage_mismatch() -> None:
    payload = result_payload()
    payload["units"] = [clean_unit(0, 0, source_id="other-source")]

    with pytest.raises(ValidationError, match="unit source_id must match"):
        CleaningResult.model_validate(payload)


def test_cleaning_result_rejects_dropped_source_type_mismatch() -> None:
    payload = result_payload()
    dropped = dropped_unit_payload()
    dropped["source_type"] = SourceType.url
    payload["dropped_units"] = [DroppedUnit.model_validate(dropped)]

    with pytest.raises(
        ValidationError,
        match="dropped unit source_type must match",
    ):
        CleaningResult.model_validate(payload)


def test_cleaning_result_rejects_emitted_and_dropped_raw_id_overlap() -> None:
    payload = result_payload()
    dropped = dropped_unit_payload()
    dropped["raw_unit_id"] = "raw:document-001:000000"
    payload["dropped_units"] = [DroppedUnit.model_validate(dropped)]

    with pytest.raises(
        ValidationError,
        match="raw_unit_id cannot be both emitted and dropped",
    ):
        CleaningResult.model_validate(payload)


def test_cleaning_result_rejects_duplicate_dropped_unit_indexes() -> None:
    payload = result_payload()
    payload["dropped_units"] = [
        DroppedUnit.model_validate(dropped_unit_payload(1)),
        DroppedUnit.model_validate(
            {
                **dropped_unit_payload(1),
                "raw_unit_id": "raw:document-001:000003",
            }
        ),
    ]
    payload["stats"] = CleaningStats.model_validate(
        stats_payload(
            total_input_units=3,
            total_output_units=1,
            dropped_unit_count=2,
        )
    )

    with pytest.raises(
        ValidationError,
        match="dropped unit_index values must be unique",
    ):
        CleaningResult.model_validate(payload)


def test_cleaning_result_rejects_dropped_units_out_of_raw_order() -> None:
    payload = result_payload()
    payload["dropped_units"] = [
        DroppedUnit.model_validate(dropped_unit_payload(3)),
        DroppedUnit.model_validate(dropped_unit_payload(1)),
    ]
    payload["stats"] = CleaningStats.model_validate(
        stats_payload(
            total_input_units=3,
            total_output_units=1,
            dropped_unit_count=2,
        )
    )

    with pytest.raises(ValidationError, match="ordered by unit_index"):
        CleaningResult.model_validate(payload)


def test_cleaning_result_rejects_multiple_cleaned_at_values() -> None:
    payload = result_payload()
    payload["units"] = [
        clean_unit(0, 0),
        clean_unit(1, 2, cleaned_at=datetime(2026, 6, 14, tzinfo=timezone.utc)),
    ]
    payload["stats"] = CleaningStats.model_validate(
        stats_payload(total_input_units=3, total_output_units=2, dropped_unit_count=1)
    )

    with pytest.raises(ValidationError, match="same cleaned_at"):
        CleaningResult.model_validate(payload)


@pytest.mark.parametrize(
    ("field_name", "field_value", "message"),
    [
        ("total_output_units", 2, "stats.total_output_units must match"),
        ("dropped_unit_count", 0, "stats.dropped_unit_count must match"),
        ("warning_count", 0, "stats.warning_count must match"),
        (
            "total_input_units",
            3,
            "stats.total_input_units must equal output plus dropped units",
        ),
        (
            "unchanged_unit_count",
            1,
            "modified_unit_count plus unchanged_unit_count must equal",
        ),
    ],
)
def test_cleaning_result_rejects_inconsistent_stats(
    field_name: str,
    field_value: int,
    message: str,
) -> None:
    payload = result_payload()
    stats = stats_payload()
    stats[field_name] = field_value
    payload["stats"] = CleaningStats.model_validate(stats)

    with pytest.raises(ValidationError, match=message):
        CleaningResult.model_validate(payload)


@pytest.mark.parametrize(
    "model_payload",
    [
        lambda: {
            "source_id": "source-001",
            "document_id": "document-001",
            "source_type": SourceType.pdf,
            "units": [raw_unit(0)],
            "unknown_field": "nope",
        },
        lambda: {**warning_payload(), "unknown_field": "nope"},
        lambda: {**dropped_unit_payload(), "unknown_field": "nope"},
        lambda: {**stats_payload(), "unknown_field": "nope"},
        lambda: {**result_payload(), "unknown_field": "nope"},
    ],
)
def test_cleaning_contracts_reject_unknown_fields(model_payload: object) -> None:
    payload = model_payload()
    models = [
        CleaningInput,
        CleaningWarning,
        DroppedUnit,
        CleaningStats,
        CleaningResult,
    ]
    expected_model = models[
        [
            "units" in payload and "cleaner_name" not in payload,
            "warning_code" in payload,
            "reason_code" in payload,
            "total_input_units" in payload,
            "cleaner_name" in payload,
        ].index(True)
    ]

    with pytest.raises(ValidationError):
        expected_model.model_validate(payload)
