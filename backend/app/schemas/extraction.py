from pydantic import Field, field_validator, model_validator

from app.schemas.common import NonEmptyStr, PipelineSchema
from app.schemas.document import RawDocumentUnit
from app.schemas.source import ProcessingStage, SourceType


class ExtractionInput(PipelineSchema):
    source_id: NonEmptyStr
    document_id: NonEmptyStr
    source_type: SourceType
    source_uri: NonEmptyStr | None = None
    original_filename: NonEmptyStr | None = None
    media_type: NonEmptyStr | None = None
    charset: NonEmptyStr | None = None
    content_bytes: bytes = Field(min_length=1, exclude=True, repr=False)
    extractor_config: dict[str, object] = Field(default_factory=dict)
    extra_metadata: dict[str, object] = Field(default_factory=dict)


class FetchedContent(PipelineSchema):
    original_url: NonEmptyStr
    final_url: NonEmptyStr
    content_bytes: bytes = Field(min_length=1, exclude=True, repr=False)
    media_type: NonEmptyStr | None = None
    charset: NonEmptyStr | None = None
    status_code: int = Field(ge=100, le=599)
    redirect_count: int = Field(default=0, ge=0)
    extra_metadata: dict[str, object] = Field(default_factory=dict)


class ExtractionStats(PipelineSchema):
    total_units: int = Field(ge=1)
    skipped_items: int = Field(default=0, ge=0)
    warning_count: int = Field(ge=0)
    extra_metadata: dict[str, object] = Field(default_factory=dict)


class ExtractionWarning(PipelineSchema):
    warning_code: NonEmptyStr
    message: NonEmptyStr
    stage: ProcessingStage
    item_index: int | None = Field(default=None, ge=0)
    unit_index: int | None = Field(default=None, ge=0)
    extra_metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("stage")
    @classmethod
    def stage_must_be_extraction_stage(
        cls, value: ProcessingStage
    ) -> ProcessingStage:
        allowed_stages = {ProcessingStage.parsing, ProcessingStage.extracting}
        if value not in allowed_stages:
            raise ValueError("stage must be parsing or extracting")
        return value


class ExtractionResult(PipelineSchema):
    source_id: NonEmptyStr
    document_id: NonEmptyStr
    source_type: SourceType
    extractor_name: NonEmptyStr
    extractor_version: NonEmptyStr
    units: list[RawDocumentUnit] = Field(min_length=1)
    warnings: list[ExtractionWarning] = Field(default_factory=list)
    stats: ExtractionStats

    @model_validator(mode="after")
    def validate_extraction_result(self) -> "ExtractionResult":
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
                raise ValueError("unit source_id must match result source_id")
            if unit.document_id != self.document_id:
                raise ValueError("unit document_id must match result document_id")
            if unit.source_type is not self.source_type:
                raise ValueError("unit source_type must match result source_type")

        if self.stats.total_units != len(self.units):
            raise ValueError("stats.total_units must match units length")

        if self.stats.warning_count != len(self.warnings):
            raise ValueError("stats.warning_count must match warnings length")

        return self
