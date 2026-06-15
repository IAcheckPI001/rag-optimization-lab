from datetime import datetime
from enum import Enum
from hashlib import sha256

from pydantic import Field, computed_field, field_validator, model_validator

from app.schemas.common import NonEmptyStr, PipelineSchema
from app.schemas.source import SourceType


class DocumentContentType(str, Enum):
    page = "page"
    section = "section"
    paragraph = "paragraph"
    table = "table"
    list = "list"
    code = "code"
    unknown = "unknown"


class DocumentUnitBase(PipelineSchema):
    document_id: NonEmptyStr
    source_id: NonEmptyStr
    source_type: SourceType
    source_uri: str | None = None
    content: str
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    section: str | None = None
    heading_path: list[NonEmptyStr] = Field(default_factory=list)
    content_type: DocumentContentType = DocumentContentType.unknown
    extra_metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content must not be blank")
        return value

    @model_validator(mode="after")
    def validate_page_range(self) -> "DocumentUnitBase":
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

    @computed_field
    @property
    def character_count(self) -> int:
        return len(self.content)

    @computed_field
    @property
    def word_count(self) -> int:
        return len(self.content.split())

    @computed_field
    @property
    def content_hash(self) -> str:
        return sha256(self.content.encode("utf-8")).hexdigest()


class RawDocumentUnit(DocumentUnitBase):
    raw_unit_id: NonEmptyStr
    unit_index: int = Field(ge=0)
    extracted_at: datetime


class CleanDocumentUnit(DocumentUnitBase):
    clean_unit_id: NonEmptyStr
    clean_unit_index: int = Field(ge=0)
    raw_unit_id: NonEmptyStr
    transformations: list[NonEmptyStr] = Field(default_factory=list)
    cleaned_at: datetime


class DocumentChunk(DocumentUnitBase):
    chunk_id: NonEmptyStr
    clean_unit_id: NonEmptyStr
    chunk_index: int = Field(ge=0)
    start_char: int | None = Field(default=None, ge=0)
    end_char: int | None = Field(default=None, ge=0)
    token_count: int | None = Field(default=None, ge=1)
    chunker_name: NonEmptyStr
    chunker_version: str | None = None
    created_at: datetime

    @model_validator(mode="after")
    def validate_offsets(self) -> "DocumentChunk":
        if self.end_char is not None and self.start_char is None:
            raise ValueError("start_char is required when end_char is provided")

        if (
            self.start_char is not None
            and self.end_char is not None
            and self.end_char <= self.start_char
        ):
            raise ValueError("end_char must be greater than start_char")

        return self
