from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from app.rag.cleaning.errors import (
    CleaningInputError,
    CleaningInvariantError,
    CleaningLimitError,
    CleaningNoContentError,
)
from app.rag.cleaning.ids import build_clean_unit_id
from app.rag.cleaning.normalization import NormalizedContent, normalize_content
from app.rag.cleaning.source_filters import (
    HTML_READING_TIME,
    HTML_UI_NOISE,
    PDF_PAGE_NUMBER,
    POSSIBLE_PAGE_NUMBER,
    SourceFilterDecision,
    apply_source_filters,
)
from app.schemas.cleaning import (
    CleaningInput,
    CleaningResult,
    CleaningStats,
    CleaningWarning,
    DroppedUnit,
)
from app.schemas.document import CleanDocumentUnit, RawDocumentUnit
from app.schemas.source import ProcessingStage


EMPTY_AFTER_NORMALIZATION = "empty_after_normalization"
SERVICE_METADATA_KEY = "cleaning"
SAFE_DROPPED_METADATA_KEYS = frozenset(
    {
        "block_type",
        "block_index",
        "page_number",
        "page_block_index",
        "document_block_index",
        "bbox",
        "page_index",
        "page_width",
        "page_height",
        "html_tag",
        "nearest_semantic_container",
        "serialization_format",
    }
)
POLICY_OVERRIDE_KEYS = frozenset(
    {
        "max_input_units",
        "max_input_characters",
        "max_output_units",
        "max_output_characters",
    }
)


@dataclass(frozen=True)
class CleaningPolicy:
    max_input_units: int = 50_000
    max_input_characters: int = 20_000_000
    max_output_units: int = 50_000
    max_output_characters: int = 20_000_000

    def __post_init__(self) -> None:
        for field_name in POLICY_OVERRIDE_KEYS:
            value = getattr(self, field_name)
            _validate_limit_value(field_name, value)


@dataclass(frozen=True)
class _DropDecision:
    reason_code: str
    message: str


class _WarningOrigin(str, Enum):
    normalization = "normalization"
    source_filter = "source_filter"
    deduplication = "deduplication"


@dataclass(frozen=True)
class _CandidateWarning:
    warning_code: str
    message: str
    extra_metadata: Mapping[str, object]
    origin: _WarningOrigin


@dataclass(frozen=True)
class _CleanCandidate:
    raw_unit: RawDocumentUnit
    normalized: NormalizedContent
    drop: _DropDecision | None = None
    candidate_warnings: tuple[_CandidateWarning, ...] = ()


class RuleBasedDocumentCleaner:
    cleaner_name = "rule_based_document_cleaner"
    cleaner_version = "0.1.0"

    def __init__(
        self,
        *,
        policy: CleaningPolicy | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.policy = policy or CleaningPolicy()
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def clean(self, input_data: CleaningInput) -> CleaningResult:
        effective_policy = _effective_policy(self.policy, input_data.cleaner_config)
        _reject_service_metadata_conflicts(input_data.units)
        _enforce_input_limits(input_data, effective_policy)

        candidates = [_build_candidate(raw_unit) for raw_unit in input_data.units]
        emitted_candidates = [
            candidate for candidate in candidates if candidate.drop is None
        ]
        dropped_candidates = [
            candidate for candidate in candidates if candidate.drop is not None
        ]

        if not emitted_candidates:
            raise CleaningNoContentError(
                "Cleaning produced no content.",
                details={
                    "source_id": input_data.source_id,
                    "document_id": input_data.document_id,
                    "source_type": input_data.source_type.value,
                    "total_input_units": len(input_data.units),
                    "dropped_unit_count": len(dropped_candidates),
                    "reason_code": _no_content_reason_code(dropped_candidates),
                },
            )

        cleaned_at = _run_timestamp(self.clock)
        units, dropped_units, warnings = _finalize_candidates(
            candidates,
            cleaner_name=self.cleaner_name,
            cleaner_version=self.cleaner_version,
            cleaned_at=cleaned_at,
        )
        _enforce_output_limits(input_data, units, effective_policy)

        stats = _build_stats(
            input_units=input_data.units,
            output_units=units,
            dropped_units=dropped_units,
            warnings=warnings,
            candidate_warnings=_candidate_warnings(candidates),
        )

        return CleaningResult(
            source_id=input_data.source_id,
            document_id=input_data.document_id,
            source_type=input_data.source_type,
            cleaner_name=self.cleaner_name,
            cleaner_version=self.cleaner_version,
            units=units,
            dropped_units=dropped_units,
            warnings=warnings,
            stats=stats,
        )


def is_blank_after_normalization(content: str) -> bool:
    return content == "" or all(character.isspace() for character in content)


def _effective_policy(
    base_policy: CleaningPolicy,
    cleaner_config: Mapping[str, object],
) -> CleaningPolicy:
    unknown_keys = set(cleaner_config).difference(POLICY_OVERRIDE_KEYS)
    if unknown_keys:
        formatted = ", ".join(sorted(unknown_keys))
        raise CleaningInputError(
            f"cleaner_config contains unsupported keys: {formatted}."
        )

    overrides: dict[str, int] = {}
    for key, value in cleaner_config.items():
        _validate_limit_value(key, value)
        overrides[key] = value

    if not overrides:
        return base_policy

    return CleaningPolicy(
        max_input_units=overrides.get(
            "max_input_units",
            base_policy.max_input_units,
        ),
        max_input_characters=overrides.get(
            "max_input_characters",
            base_policy.max_input_characters,
        ),
        max_output_units=overrides.get(
            "max_output_units",
            base_policy.max_output_units,
        ),
        max_output_characters=overrides.get(
            "max_output_characters",
            base_policy.max_output_characters,
        ),
    )


def _validate_limit_value(field_name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CleaningInputError(f"{field_name} must be an integer greater than 0.")

    if value < 1:
        raise CleaningInputError(f"{field_name} must be greater than 0.")


def _reject_service_metadata_conflicts(units: list[RawDocumentUnit]) -> None:
    for unit in units:
        if SERVICE_METADATA_KEY in unit.extra_metadata:
            raise CleaningInputError(
                "raw unit extra_metadata contains reserved cleaning key",
                details={"raw_unit_id": unit.raw_unit_id, "unit_index": unit.unit_index},
            )


def _enforce_input_limits(
    input_data: CleaningInput,
    policy: CleaningPolicy,
) -> None:
    input_unit_count = len(input_data.units)
    if input_unit_count > policy.max_input_units:
        raise CleaningLimitError(
            "Cleaning input unit limit exceeded.",
            details={
                "source_id": input_data.source_id,
                "document_id": input_data.document_id,
                "source_type": input_data.source_type.value,
                "limit_name": "max_input_units",
                "actual_count": input_unit_count,
                "configured_limit": policy.max_input_units,
            },
        )

    input_character_count = sum(unit.character_count for unit in input_data.units)
    if input_character_count > policy.max_input_characters:
        raise CleaningLimitError(
            "Cleaning input character limit exceeded.",
            details={
                "source_id": input_data.source_id,
                "document_id": input_data.document_id,
                "source_type": input_data.source_type.value,
                "limit_name": "max_input_characters",
                "actual_count": input_character_count,
                "configured_limit": policy.max_input_characters,
            },
        )


def _enforce_output_limits(
    input_data: CleaningInput,
    output_units: list[CleanDocumentUnit],
    policy: CleaningPolicy,
) -> None:
    output_unit_count = len(output_units)
    if output_unit_count > policy.max_output_units:
        raise CleaningLimitError(
            "Cleaning output unit limit exceeded.",
            details={
                "source_id": input_data.source_id,
                "document_id": input_data.document_id,
                "source_type": input_data.source_type.value,
                "limit_name": "max_output_units",
                "actual_count": output_unit_count,
                "configured_limit": policy.max_output_units,
            },
        )

    output_character_count = sum(unit.character_count for unit in output_units)
    if output_character_count > policy.max_output_characters:
        raise CleaningLimitError(
            "Cleaning output character limit exceeded.",
            details={
                "source_id": input_data.source_id,
                "document_id": input_data.document_id,
                "source_type": input_data.source_type.value,
                "limit_name": "max_output_characters",
                "actual_count": output_character_count,
                "configured_limit": policy.max_output_characters,
            },
        )


def _build_candidate(raw_unit: RawDocumentUnit) -> _CleanCandidate:
    normalized = normalize_content(
        raw_unit.content,
        content_type=raw_unit.content_type,
        extra_metadata=raw_unit.extra_metadata,
    )
    candidate_warnings = _normalization_candidate_warnings(normalized)
    drop = None
    if is_blank_after_normalization(normalized.content):
        drop = _DropDecision(
            reason_code=EMPTY_AFTER_NORMALIZATION,
            message="Unit became empty after normalization.",
        )
        return _CleanCandidate(
            raw_unit=raw_unit,
            normalized=normalized,
            drop=drop,
            candidate_warnings=candidate_warnings,
        )

    source_filter_decision = apply_source_filters(raw_unit, normalized.content)
    drop = _source_filter_drop(source_filter_decision)
    candidate_warnings = (
        *candidate_warnings,
        *_source_filter_candidate_warnings(source_filter_decision),
    )

    return _CleanCandidate(
        raw_unit=raw_unit,
        normalized=normalized,
        drop=drop,
        candidate_warnings=candidate_warnings,
    )


def _normalization_candidate_warnings(
    normalized: NormalizedContent,
) -> tuple[_CandidateWarning, ...]:
    return tuple(
        _CandidateWarning(
            warning_code=warning.warning_code,
            message=warning.message,
            extra_metadata=dict(warning.extra_metadata or {}),
            origin=_WarningOrigin.normalization,
        )
        for warning in normalized.warnings
    )


def _source_filter_drop(
    decision: SourceFilterDecision,
) -> _DropDecision | None:
    if decision.drop_reason_code is None:
        return None

    if decision.drop_message is None:
        raise CleaningInvariantError("source filter drop must include a message")

    return _DropDecision(
        reason_code=decision.drop_reason_code,
        message=decision.drop_message,
    )


def _source_filter_candidate_warnings(
    decision: SourceFilterDecision,
) -> tuple[_CandidateWarning, ...]:
    return tuple(
        _CandidateWarning(
            warning_code=warning.warning_code,
            message=warning.message,
            extra_metadata=dict(warning.extra_metadata),
            origin=_WarningOrigin.source_filter,
        )
        for warning in decision.warnings
    )


def _run_timestamp(clock: Callable[[], datetime]) -> datetime:
    timestamp = clock()
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise CleaningInvariantError("cleaned_at clock must return timezone-aware datetime")

    return timestamp.astimezone(timezone.utc)


def _finalize_candidates(
    candidates: list[_CleanCandidate],
    *,
    cleaner_name: str,
    cleaner_version: str,
    cleaned_at: datetime,
) -> tuple[list[CleanDocumentUnit], list[DroppedUnit], list[CleaningWarning]]:
    units: list[CleanDocumentUnit] = []
    dropped_units: list[DroppedUnit] = []
    warnings: list[CleaningWarning] = []

    for candidate in candidates:
        if candidate.drop is None:
            clean_unit_index = len(units)
            clean_unit = _build_clean_unit(
                candidate,
                clean_unit_index=clean_unit_index,
                cleaner_name=cleaner_name,
                cleaner_version=cleaner_version,
                cleaned_at=cleaned_at,
            )
            units.append(clean_unit)
            warnings.extend(
                _public_warnings(
                    candidate,
                    clean_unit_index=clean_unit_index,
                )
            )
            continue

        dropped_units.append(_build_dropped_unit(candidate))
        warnings.extend(_public_warnings(candidate, clean_unit_index=None))

    return units, dropped_units, warnings


def _build_clean_unit(
    candidate: _CleanCandidate,
    *,
    clean_unit_index: int,
    cleaner_name: str,
    cleaner_version: str,
    cleaned_at: datetime,
) -> CleanDocumentUnit:
    raw = candidate.raw_unit
    return CleanDocumentUnit(
        document_id=raw.document_id,
        source_id=raw.source_id,
        source_type=raw.source_type,
        source_uri=raw.source_uri,
        content=candidate.normalized.content,
        page_start=raw.page_start,
        page_end=raw.page_end,
        section=raw.section,
        heading_path=list(raw.heading_path),
        content_type=raw.content_type,
        extra_metadata={
            **dict(raw.extra_metadata),
            SERVICE_METADATA_KEY: {
                "cleaner": cleaner_name,
                "cleaner_version": cleaner_version,
                "modified": candidate.normalized.content != raw.content,
            },
        },
        clean_unit_id=build_clean_unit_id(raw.document_id, raw.unit_index),
        clean_unit_index=clean_unit_index,
        raw_unit_id=raw.raw_unit_id,
        transformations=list(candidate.normalized.transformations),
        cleaned_at=cleaned_at,
    )


def _build_dropped_unit(candidate: _CleanCandidate) -> DroppedUnit:
    raw = candidate.raw_unit
    if candidate.drop is None:
        raise CleaningInvariantError("dropped candidate must include a drop decision")

    return DroppedUnit(
        raw_unit_id=raw.raw_unit_id,
        unit_index=raw.unit_index,
        reason_code=candidate.drop.reason_code,
        message=candidate.drop.message,
        original_content_hash=raw.content_hash,
        source_type=raw.source_type,
        page_start=raw.page_start,
        page_end=raw.page_end,
        section=raw.section,
        content_type=raw.content_type,
        extra_metadata=_safe_dropped_metadata(raw.extra_metadata),
    )


def _safe_dropped_metadata(extra_metadata: Mapping[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in extra_metadata.items()
        if key in SAFE_DROPPED_METADATA_KEYS
    }


def _public_warnings(
    candidate: _CleanCandidate,
    *,
    clean_unit_index: int | None,
) -> list[CleaningWarning]:
    return [
        CleaningWarning(
            warning_code=warning.warning_code,
            message=warning.message,
            stage=ProcessingStage.cleaning,
            raw_unit_id=candidate.raw_unit.raw_unit_id,
            clean_unit_index=clean_unit_index,
            extra_metadata=dict(warning.extra_metadata or {}),
        )
        for warning in candidate.candidate_warnings
    ]


def _build_stats(
    *,
    input_units: list[RawDocumentUnit],
    output_units: list[CleanDocumentUnit],
    dropped_units: list[DroppedUnit],
    warnings: list[CleaningWarning],
    candidate_warnings: list[_CandidateWarning],
) -> CleaningStats:
    output_by_raw_id = {unit.raw_unit_id: unit for unit in output_units}
    modified_unit_count = 0
    unchanged_unit_count = 0
    for raw in input_units:
        clean = output_by_raw_id.get(raw.raw_unit_id)
        if clean is None:
            continue
        if clean.content != raw.content:
            modified_unit_count += 1
        else:
            unchanged_unit_count += 1

    characters_before = sum(unit.character_count for unit in input_units)
    characters_after = sum(unit.character_count for unit in output_units)
    empty_after_normalization_count = sum(
        1
        for unit in dropped_units
        if unit.reason_code == EMPTY_AFTER_NORMALIZATION
    )
    html_ui_noise_dropped_count = sum(
        1 for unit in dropped_units if unit.reason_code == HTML_UI_NOISE
    )
    html_reading_time_dropped_count = sum(
        1 for unit in dropped_units if unit.reason_code == HTML_READING_TIME
    )
    pdf_page_number_dropped_count = sum(
        1 for unit in dropped_units if unit.reason_code == PDF_PAGE_NUMBER
    )
    normalization_warning_count = sum(
        1
        for warning in candidate_warnings
        if warning.origin is _WarningOrigin.normalization
    )
    source_filter_warning_count = sum(
        1
        for warning in candidate_warnings
        if warning.origin is _WarningOrigin.source_filter
    )
    possible_page_number_warning_count = sum(
        1
        for warning in candidate_warnings
        if warning.warning_code == POSSIBLE_PAGE_NUMBER
    )

    return CleaningStats(
        total_input_units=len(input_units),
        total_output_units=len(output_units),
        dropped_unit_count=len(dropped_units),
        modified_unit_count=modified_unit_count,
        unchanged_unit_count=unchanged_unit_count,
        warning_count=len(warnings),
        characters_before=characters_before,
        characters_after=characters_after,
        extra_metadata={
            "empty_after_normalization_count": empty_after_normalization_count,
            "html_ui_noise_dropped_count": html_ui_noise_dropped_count,
            "html_reading_time_dropped_count": html_reading_time_dropped_count,
            "pdf_page_number_dropped_count": pdf_page_number_dropped_count,
            "normalization_warning_count": normalization_warning_count,
            "source_filter_warning_count": source_filter_warning_count,
            "possible_page_number_warning_count": possible_page_number_warning_count,
            "modified_character_delta": characters_before - characters_after,
        },
    )


def _candidate_warnings(candidates: list[_CleanCandidate]) -> list[_CandidateWarning]:
    return [
        warning
        for candidate in candidates
        for warning in candidate.candidate_warnings
    ]


def _no_content_reason_code(dropped_candidates: list[_CleanCandidate]) -> str:
    reason_codes = {
        candidate.drop.reason_code
        for candidate in dropped_candidates
        if candidate.drop is not None
    }
    if len(reason_codes) == 1:
        return next(iter(reason_codes))

    return "all_units_dropped"
