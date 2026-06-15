from pydantic import Field, field_validator, model_validator

from app.schemas.common import NonEmptyStr, PipelineSchema
from app.schemas.document import CleanDocumentUnit, DocumentContentType, RawDocumentUnit
from app.schemas.source import ProcessingStage, SourceType


class CleaningInput(PipelineSchema):
    source_id: NonEmptyStr
    document_id: NonEmptyStr
    source_type: SourceType
    units: list[RawDocumentUnit] = Field(min_length=1)
    cleaner_config: dict[str, object] = Field(default_factory=dict)
    extra_metadata: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_input_units(self) -> "CleaningInput":
        raw_unit_ids = [unit.raw_unit_id for unit in self.units]
        if len(raw_unit_ids) != len(set(raw_unit_ids)):
            raise ValueError("raw_unit_id values must be unique")

        unit_indexes = [unit.unit_index for unit in self.units]
        if len(unit_indexes) != len(set(unit_indexes)):
            raise ValueError("unit_index values must be unique")

        expected_indexes = list(range(len(self.units)))
        if unit_indexes != expected_indexes:
            raise ValueError("unit_index values must be continuous and ordered from 0")

        for unit in self.units:
            if unit.source_id != self.source_id:
                raise ValueError("unit source_id must match input source_id")
            if unit.document_id != self.document_id:
                raise ValueError("unit document_id must match input document_id")
            if unit.source_type is not self.source_type:
                raise ValueError("unit source_type must match input source_type")

        return self


class CleaningWarning(PipelineSchema):
    warning_code: NonEmptyStr
    message: NonEmptyStr
    stage: ProcessingStage
    raw_unit_id: NonEmptyStr | None = None
    clean_unit_index: int | None = Field(default=None, ge=0)
    extra_metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("stage")
    @classmethod
    def stage_must_be_cleaning(cls, value: ProcessingStage) -> ProcessingStage:
        if value is not ProcessingStage.cleaning:
            raise ValueError("stage must be cleaning")
        return value


class DroppedUnit(PipelineSchema):
    raw_unit_id: NonEmptyStr
    unit_index: int = Field(ge=0)
    reason_code: NonEmptyStr
    message: NonEmptyStr
    original_content_hash: NonEmptyStr
    source_type: SourceType
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    section: str | None = None
    content_type: DocumentContentType = DocumentContentType.unknown
    extra_metadata: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_page_range(self) -> "DroppedUnit":
        if self.page_end is not None and self.page_start is None:
            raise ValueError("page_start is required when page_end is provided")

        if self.page_start is not None and self.page_end is None:
            raise ValueError("page_end is required when page_start is provided")

        if (
            self.page_start is not None
            and self.page_end is not None
            and self.page_end < self.page_start
        ):
            raise ValueError("page_end must be greater than or equal to page_start")

        return self


class CleaningStats(PipelineSchema):
    total_input_units: int = Field(ge=1)
    total_output_units: int = Field(ge=0)
    dropped_unit_count: int = Field(ge=0)
    modified_unit_count: int = Field(ge=0)
    unchanged_unit_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    characters_before: int = Field(ge=0)
    characters_after: int = Field(ge=0)
    extra_metadata: dict[str, object] = Field(default_factory=dict)


class CleaningResult(PipelineSchema):
    source_id: NonEmptyStr
    document_id: NonEmptyStr
    source_type: SourceType
    cleaner_name: NonEmptyStr
    cleaner_version: NonEmptyStr
    units: list[CleanDocumentUnit] = Field(min_length=1)
    dropped_units: list[DroppedUnit] = Field(default_factory=list)
    warnings: list[CleaningWarning] = Field(default_factory=list)
    stats: CleaningStats

    @model_validator(mode="after")
    def validate_cleaning_result(self) -> "CleaningResult":
        clean_unit_ids = [unit.clean_unit_id for unit in self.units]
        if len(clean_unit_ids) != len(set(clean_unit_ids)):
            raise ValueError("clean_unit_id values must be unique")

        clean_unit_indexes = [unit.clean_unit_index for unit in self.units]
        if len(clean_unit_indexes) != len(set(clean_unit_indexes)):
            raise ValueError("clean_unit_index values must be unique")

        expected_clean_indexes = list(range(len(self.units)))
        if clean_unit_indexes != expected_clean_indexes:
            raise ValueError(
                "clean_unit_index values must be continuous and ordered from 0"
            )

        for unit in self.units:
            if unit.source_id != self.source_id:
                raise ValueError("unit source_id must match result source_id")
            if unit.document_id != self.document_id:
                raise ValueError("unit document_id must match result document_id")
            if unit.source_type is not self.source_type:
                raise ValueError("unit source_type must match result source_type")

        dropped_unit_indexes = [unit.unit_index for unit in self.dropped_units]
        if len(dropped_unit_indexes) != len(set(dropped_unit_indexes)):
            raise ValueError("dropped unit_index values must be unique")

        if dropped_unit_indexes != sorted(dropped_unit_indexes):
            raise ValueError("dropped units must be ordered by unit_index")

        emitted_raw_unit_ids = {unit.raw_unit_id for unit in self.units}
        dropped_raw_unit_ids = {unit.raw_unit_id for unit in self.dropped_units}
        if emitted_raw_unit_ids & dropped_raw_unit_ids:
            raise ValueError("raw_unit_id cannot be both emitted and dropped")

        for dropped_unit in self.dropped_units:
            if dropped_unit.source_type is not self.source_type:
                raise ValueError(
                    "dropped unit source_type must match result source_type"
                )

        cleaned_at_values = {unit.cleaned_at for unit in self.units}
        if len(cleaned_at_values) != 1:
            raise ValueError("all clean units must share the same cleaned_at")

        if self.stats.total_output_units != len(self.units):
            raise ValueError("stats.total_output_units must match units length")

        if self.stats.dropped_unit_count != len(self.dropped_units):
            raise ValueError(
                "stats.dropped_unit_count must match dropped_units length"
            )

        if self.stats.warning_count != len(self.warnings):
            raise ValueError("stats.warning_count must match warnings length")

        expected_input_units = (
            self.stats.total_output_units + self.stats.dropped_unit_count
        )
        if self.stats.total_input_units != expected_input_units:
            raise ValueError(
                "stats.total_input_units must equal output plus dropped units"
            )

        accounted_output_units = (
            self.stats.modified_unit_count + self.stats.unchanged_unit_count
        )
        if accounted_output_units != self.stats.total_output_units:
            raise ValueError(
                "modified_unit_count plus unchanged_unit_count must equal output units"
            )

        return self
