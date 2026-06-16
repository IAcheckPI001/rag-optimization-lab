from datetime import datetime, timezone, timedelta

import pytest

from app.rag.cleaning.errors import (
    CleaningInputError,
    CleaningInvariantError,
    CleaningLimitError,
    CleaningNoContentError,
)
from app.rag.cleaning.rule_based_cleaner import (
    EMPTY_AFTER_NORMALIZATION,
    CleaningPolicy,
    RuleBasedDocumentCleaner,
    is_blank_after_normalization,
)
from app.schemas.cleaning import CleaningInput
from app.schemas.document import DocumentContentType, RawDocumentUnit
from app.schemas.source import ProcessingStage, SourceType


FIXED_TIME = datetime(2026, 6, 13, 10, 30, tzinfo=timezone.utc)


class CountingClock:
    def __init__(self, timestamp: datetime = FIXED_TIME) -> None:
        self.timestamp = timestamp
        self.calls = 0

    def __call__(self) -> datetime:
        self.calls += 1
        return self.timestamp


def raw_unit_payload(
    unit_index: int = 0,
    content: str = "Raw content",
    *,
    raw_unit_id: str | None = None,
    content_type: DocumentContentType = DocumentContentType.paragraph,
    extra_metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "document_id": "document-001",
        "source_id": "source-001",
        "source_type": SourceType.pdf,
        "source_uri": "storage://sources/source-001/raw.pdf",
        "content": content,
        "page_start": unit_index + 1,
        "page_end": unit_index + 1,
        "section": "Policy",
        "heading_path": ["Policy"],
        "content_type": content_type,
        "extra_metadata": extra_metadata
        if extra_metadata is not None
        else {
            "block_type": "text",
            "block_index": unit_index,
            "page_number": unit_index + 1,
            "page_block_index": 0,
            "unsafe": "do-not-copy-to-dropped-audit",
        },
        "raw_unit_id": raw_unit_id or f"raw:document-001:{unit_index:06d}",
        "unit_index": unit_index,
        "extracted_at": datetime(2026, 6, 12, tzinfo=timezone.utc),
    }


def raw_unit(
    unit_index: int = 0,
    content: str = "Raw content",
    **overrides: object,
) -> RawDocumentUnit:
    payload = raw_unit_payload(unit_index, content)
    payload.update(overrides)
    return RawDocumentUnit.model_validate(payload)


def cleaning_input(
    units: list[RawDocumentUnit],
    *,
    cleaner_config: dict[str, object] | None = None,
    extra_metadata: dict[str, object] | None = None,
) -> CleaningInput:
    return CleaningInput.model_validate(
        {
            "source_id": "source-001",
            "document_id": "document-001",
            "source_type": SourceType.pdf,
            "units": units,
            "cleaner_config": cleaner_config or {},
            "extra_metadata": extra_metadata or {},
        }
    )


def cleaner(clock: CountingClock | None = None) -> RuleBasedDocumentCleaner:
    return RuleBasedDocumentCleaner(clock=clock or CountingClock())


def stable_result_dump(result) -> dict[str, object]:
    dumped = result.model_dump()
    for unit in dumped["units"]:
        unit["cleaned_at"] = unit["cleaned_at"].isoformat()
    return dumped


def test_valid_single_raw_unit_produces_one_clean_unit() -> None:
    clock = CountingClock()
    input_data = cleaning_input([raw_unit(0, "  Cafe\u0301\ttext  ")])

    result = RuleBasedDocumentCleaner(clock=clock).clean(input_data)

    assert clock.calls == 1
    assert result.cleaner_name == "rule_based_document_cleaner"
    assert result.cleaner_version == "0.1.0"
    assert len(result.units) == 1
    clean = result.units[0]
    assert clean.content == "Café text"
    assert clean.clean_unit_id == "clean:document-001:000000"
    assert clean.clean_unit_index == 0
    assert clean.raw_unit_id == "raw:document-001:000000"
    assert clean.transformations == [
        "unicode_nfc",
        "prose_whitespace_normalized",
    ]
    assert clean.cleaned_at == FIXED_TIME
    assert clean.extra_metadata["block_type"] == "text"
    assert clean.extra_metadata["cleaning"] == {
        "cleaner": "rule_based_document_cleaner",
        "cleaner_version": "0.1.0",
        "modified": True,
    }
    assert "applied_rules" not in clean.extra_metadata["cleaning"]
    assert result.dropped_units == []


def test_multiple_raw_units_preserve_relative_order() -> None:
    input_data = cleaning_input(
        [
            raw_unit(0, "First"),
            raw_unit(1, "Second"),
            raw_unit(2, "Third"),
        ]
    )

    result = cleaner().clean(input_data)

    assert [unit.content for unit in result.units] == ["First", "Second", "Third"]
    assert [unit.clean_unit_index for unit in result.units] == [0, 1, 2]
    assert [unit.clean_unit_id for unit in result.units] == [
        "clean:document-001:000000",
        "clean:document-001:000001",
        "clean:document-001:000002",
    ]


def test_dropped_middle_raw_unit_keeps_stable_ids_and_continuous_clean_indexes() -> None:
    input_data = cleaning_input(
        [
            raw_unit(0, "First"),
            raw_unit(1, "\x00"),
            raw_unit(2, "Third"),
        ]
    )

    result = cleaner().clean(input_data)

    assert [unit.clean_unit_index for unit in result.units] == [0, 1]
    assert [unit.clean_unit_id for unit in result.units] == [
        "clean:document-001:000000",
        "clean:document-001:000002",
    ]
    assert [unit.raw_unit_id for unit in result.units] == [
        "raw:document-001:000000",
        "raw:document-001:000002",
    ]
    assert [unit.unit_index for unit in result.dropped_units] == [1]
    assert result.dropped_units[0].reason_code == EMPTY_AFTER_NORMALIZATION


def test_clean_id_generation_uses_raw_unit_index_not_raw_unit_id_string() -> None:
    input_data = cleaning_input(
        [
            raw_unit(
                0,
                "First",
                raw_unit_id="raw:not-the-document:999999",
            )
        ]
    )

    result = cleaner().clean(input_data)

    assert result.units[0].clean_unit_id == "clean:document-001:000000"
    assert result.units[0].raw_unit_id == "raw:not-the-document:999999"


def test_all_clean_units_share_one_injected_cleaned_at() -> None:
    clock = CountingClock()
    input_data = cleaning_input([raw_unit(0, "First"), raw_unit(1, "Second")])

    result = RuleBasedDocumentCleaner(clock=clock).clean(input_data)

    assert clock.calls == 1
    assert {unit.cleaned_at for unit in result.units} == {FIXED_TIME}


def test_naive_clock_result_raises_cleaning_invariant_error() -> None:
    clock = CountingClock(datetime(2026, 6, 13, 10, 30))
    input_data = cleaning_input([raw_unit(0, "Content")])

    with pytest.raises(CleaningInvariantError, match="timezone-aware"):
        RuleBasedDocumentCleaner(clock=clock).clean(input_data)

    assert clock.calls == 1


def test_aware_non_utc_clock_result_is_normalized_to_utc() -> None:
    non_utc_time = datetime(
        2026,
        6,
        13,
        17,
        30,
        tzinfo=timezone(timedelta(hours=7)),
    )
    input_data = cleaning_input([raw_unit(0, "Content")])

    result = RuleBasedDocumentCleaner(clock=CountingClock(non_utc_time)).clean(
        input_data
    )

    assert result.units[0].cleaned_at == FIXED_TIME
    assert result.units[0].cleaned_at.tzinfo is timezone.utc


@pytest.mark.parametrize(
    "content",
    ["", "   ", "\t\n", "\u00a0", "\n\t\u00a0"],
)
def test_blank_helper_treats_common_whitespace_as_blank(content: str) -> None:
    assert is_blank_after_normalization(content) is True


@pytest.mark.parametrize("content", ["\u200b", "\ufeff"])
def test_blank_helper_does_not_treat_format_only_content_as_blank(
    content: str,
) -> None:
    assert is_blank_after_normalization(content) is False


def test_blank_after_normalization_creates_dropped_unit() -> None:
    raw = raw_unit(0, "\x00")
    input_data = cleaning_input([raw, raw_unit(1, "Content")])

    result = cleaner().clean(input_data)

    dropped = result.dropped_units[0]
    assert dropped.raw_unit_id == raw.raw_unit_id
    assert dropped.unit_index == raw.unit_index
    assert dropped.reason_code == EMPTY_AFTER_NORMALIZATION
    assert dropped.message == "Unit became empty after normalization."
    assert dropped.original_content_hash == raw.content_hash
    assert dropped.source_type is raw.source_type
    assert dropped.page_start == raw.page_start
    assert dropped.page_end == raw.page_end
    assert dropped.section == raw.section
    assert dropped.content_type is raw.content_type


def test_all_blank_results_raise_no_content_without_clock_or_partial_result() -> None:
    clock = CountingClock()
    input_data = cleaning_input([raw_unit(0, "\x00"), raw_unit(1, "\x7f")])

    with pytest.raises(CleaningNoContentError) as exc_info:
        RuleBasedDocumentCleaner(clock=clock).clean(input_data)

    assert clock.calls == 0
    assert exc_info.value.details == {
        "source_id": "source-001",
        "document_id": "document-001",
        "source_type": "pdf",
        "total_input_units": 2,
        "dropped_unit_count": 2,
        "reason_code": EMPTY_AFTER_NORMALIZATION,
    }
    assert "\x00" not in str(exc_info.value.details)
    assert "dropped_units" not in exc_info.value.details


def test_dropped_records_omit_full_content_and_copy_only_safe_metadata() -> None:
    raw = raw_unit(
        0,
        "\x00",
        extra_metadata={
            "block_type": "text",
            "block_index": 7,
            "page_number": 3,
            "page_block_index": 2,
            "document_block_index": 9,
            "html_tag": "p",
            "serialization_format": "tsv_escaped_v1",
            "content_bytes": b"secret",
            "raw_content": "full content",
            "unsafe": "nope",
        },
    )
    input_data = cleaning_input([raw, raw_unit(1, "Content")])

    result = cleaner().clean(input_data)

    assert result.dropped_units[0].extra_metadata == {
        "block_type": "text",
        "block_index": 7,
        "page_number": 3,
        "page_block_index": 2,
        "document_block_index": 9,
        "html_tag": "p",
        "serialization_format": "tsv_escaped_v1",
    }


def test_raw_metadata_is_preserved_for_emitted_clean_units() -> None:
    metadata = {
        "block_type": "paragraph",
        "parser_details": {"cleaning": "literal source field"},
    }
    input_data = cleaning_input([raw_unit(0, "Content", extra_metadata=metadata)])

    result = cleaner().clean(input_data)

    assert result.units[0].extra_metadata["block_type"] == "paragraph"
    assert result.units[0].extra_metadata["parser_details"] == {
        "cleaning": "literal source field"
    }
    assert "cleaning" in result.units[0].extra_metadata


def test_top_level_raw_cleaning_metadata_conflict_is_rejected_without_clock() -> None:
    clock = CountingClock()
    input_data = cleaning_input(
        [
            raw_unit(
                0,
                "Sensitive content",
                extra_metadata={"cleaning": {"caller": "value"}},
            )
        ]
    )

    with pytest.raises(CleaningInputError) as exc_info:
        RuleBasedDocumentCleaner(clock=clock).clean(input_data)

    assert clock.calls == 0
    assert "Sensitive content" not in str(exc_info.value)
    assert exc_info.value.details == {
        "raw_unit_id": "raw:document-001:000000",
        "unit_index": 0,
    }


def test_input_level_cleaning_metadata_is_not_rejected_in_phase_3_3() -> None:
    input_data = cleaning_input(
        [raw_unit(0, "Content")],
        extra_metadata={"cleaning": {"run": "metadata"}},
    )

    result = cleaner().clean(input_data)

    assert result.units[0].content == "Content"


def test_cleaner_config_allowed_overrides_apply_per_run() -> None:
    input_data = cleaning_input(
        [raw_unit(0, "Content")],
        cleaner_config={"max_input_units": 1, "max_output_units": 1},
    )

    result = RuleBasedDocumentCleaner(
        policy=CleaningPolicy(max_input_units=10, max_output_units=10)
    ).clean(input_data)

    assert len(result.units) == 1


def test_cleaner_config_override_precedence_can_tighten_constructor_policy() -> None:
    clock = CountingClock()
    input_data = cleaning_input(
        [raw_unit(0, "First"), raw_unit(1, "Second")],
        cleaner_config={"max_input_units": 1},
    )

    with pytest.raises(CleaningLimitError) as exc_info:
        RuleBasedDocumentCleaner(
            policy=CleaningPolicy(max_input_units=10),
            clock=clock,
        ).clean(input_data)

    assert clock.calls == 0
    assert exc_info.value.details["limit_name"] == "max_input_units"
    assert exc_info.value.details["configured_limit"] == 1


def test_unknown_cleaner_config_keys_are_rejected_without_clock() -> None:
    clock = CountingClock()
    input_data = cleaning_input(
        [raw_unit(0, "Content")],
        cleaner_config={"drop_pdf_page_numbers": True},
    )

    with pytest.raises(CleaningInputError, match="unsupported keys"):
        RuleBasedDocumentCleaner(clock=clock).clean(input_data)

    assert clock.calls == 0


@pytest.mark.parametrize("value", [True, False, 1.5, "100", None, 0, -1])
def test_invalid_cleaner_config_limit_values_are_rejected_without_clock(
    value: object,
) -> None:
    clock = CountingClock()
    input_data = cleaning_input(
        [raw_unit(0, "Content")],
        cleaner_config={"max_input_units": value},
    )

    with pytest.raises(CleaningInputError):
        RuleBasedDocumentCleaner(clock=clock).clean(input_data)

    assert clock.calls == 0


def test_constructor_policy_rejects_bool_limit_values() -> None:
    with pytest.raises(CleaningInputError):
        CleaningPolicy(max_input_units=True)


def test_stats_equations_and_character_counts_hold() -> None:
    raw_a = raw_unit(0, "  A  ")
    raw_b = raw_unit(1, "\x00")
    raw_c = raw_unit(2, "C")
    input_data = cleaning_input([raw_a, raw_b, raw_c])

    result = cleaner().clean(input_data)

    stats = result.stats
    assert stats.total_input_units == 3
    assert stats.total_output_units == 2
    assert stats.dropped_unit_count == 1
    assert stats.total_input_units == stats.total_output_units + stats.dropped_unit_count
    assert stats.modified_unit_count == 1
    assert stats.unchanged_unit_count == 1
    assert stats.modified_unit_count + stats.unchanged_unit_count == stats.total_output_units
    assert stats.warning_count == len(result.warnings)
    assert stats.characters_before == (
        raw_a.character_count + raw_b.character_count + raw_c.character_count
    )
    assert stats.characters_after == sum(unit.character_count for unit in result.units)
    assert stats.extra_metadata["empty_after_normalization_count"] == 1
    assert stats.extra_metadata["normalization_warning_count"] == len(result.warnings)
    assert stats.extra_metadata["modified_character_delta"] == (
        stats.characters_before - stats.characters_after
    )


def test_input_character_limit_failure_does_not_call_clock() -> None:
    clock = CountingClock()
    input_data = cleaning_input([raw_unit(0, "12345")])

    with pytest.raises(CleaningLimitError) as exc_info:
        RuleBasedDocumentCleaner(
            policy=CleaningPolicy(max_input_characters=4),
            clock=clock,
        ).clean(input_data)

    assert clock.calls == 0
    assert exc_info.value.details["limit_name"] == "max_input_characters"
    assert exc_info.value.details["actual_count"] == 5


def test_output_character_limit_failure_does_not_return_partial_result() -> None:
    input_data = cleaning_input([raw_unit(0, "12345")])

    with pytest.raises(CleaningLimitError) as exc_info:
        RuleBasedDocumentCleaner(
            policy=CleaningPolicy(max_output_characters=4),
        ).clean(input_data)

    assert exc_info.value.details["limit_name"] == "max_output_characters"
    assert exc_info.value.details["actual_count"] == 5


def test_normalization_warning_on_emitted_unit_gets_final_clean_unit_index() -> None:
    input_data = cleaning_input([raw_unit(0, "Bad � text")])

    result = cleaner().clean(input_data)

    assert len(result.warnings) == 1
    warning = result.warnings[0]
    assert warning.warning_code == "replacement_character_detected"
    assert warning.stage is ProcessingStage.cleaning
    assert warning.raw_unit_id == "raw:document-001:000000"
    assert warning.clean_unit_index == 0
    assert "Bad � text" not in str(warning.extra_metadata)


def test_normalization_warning_on_dropped_unit_keeps_clean_unit_index_none() -> None:
    input_data = cleaning_input([raw_unit(0, "\x00"), raw_unit(1, "Bad � text")])

    result = cleaner().clean(input_data)

    assert len(result.warnings) == 2
    dropped_warning = result.warnings[0]
    emitted_warning = result.warnings[1]
    assert dropped_warning.warning_code == "suspicious_control_characters_removed"
    assert dropped_warning.raw_unit_id == "raw:document-001:000000"
    assert dropped_warning.clean_unit_index is None
    assert emitted_warning.warning_code == "replacement_character_detected"
    assert emitted_warning.clean_unit_index == 0


def test_deterministic_stable_fields_across_repeated_runs_with_fixed_clock() -> None:
    input_data = cleaning_input(
        [
            raw_unit(0, "  Cafe\u0301  "),
            raw_unit(1, "\x00"),
            raw_unit(2, "Bad � text"),
        ]
    )

    first = RuleBasedDocumentCleaner(clock=CountingClock()).clean(input_data)
    second = RuleBasedDocumentCleaner(clock=CountingClock()).clean(input_data)

    assert stable_result_dump(first) == stable_result_dump(second)
