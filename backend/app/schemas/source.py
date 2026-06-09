from datetime import datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import Field

from app.schemas.common import NonEmptyStr, PipelineSchema


class SourceType(str, Enum):
    pdf = "pdf"
    docx = "docx"
    url = "url"


class SourceStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class ProcessingStage(str, Enum):
    queued = "queued"
    downloading = "downloading"
    parsing = "parsing"
    extracting = "extracting"
    cleaning = "cleaning"
    chunking = "chunking"
    embedding = "embedding"
    indexing = "indexing"
    completed = "completed"
    failed = "failed"


class SourceError(PipelineSchema):
    error_code: NonEmptyStr
    message: NonEmptyStr
    failed_stage: ProcessingStage
    retryable: bool = False


class BaseFileMetadata(PipelineSchema):
    title: str | None = None
    original_filename: NonEmptyStr
    checksum_sha256: str | None = None
    extra_metadata: dict[str, object] = Field(default_factory=dict)


class PdfSourceMetadata(BaseFileMetadata):
    metadata_type: Literal["pdf"] = "pdf"
    mime_type: str = "application/pdf"
    total_pages: int | None = None


class DocxSourceMetadata(BaseFileMetadata):
    metadata_type: Literal["docx"] = "docx"
    mime_type: str = (
        "application/vnd.openxmlformats-officedocument"
        ".wordprocessingml.document"
    )
    paragraph_count: int | None = None
    table_count: int | None = None


class UrlSourceMetadata(PipelineSchema):
    metadata_type: Literal["url"] = "url"
    original_url: NonEmptyStr
    final_url: str | None = None
    canonical_url: str | None = None
    domain: NonEmptyStr
    site_name: str | None = None
    title: str | None = None
    description: str | None = None
    language: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    updated_at: datetime | None = None
    crawled_at: datetime | None = None
    http_status: int | None = None
    mime_type: str | None = None
    extra_metadata: dict[str, object] = Field(default_factory=dict)


SourceMetadata = Annotated[
    PdfSourceMetadata | DocxSourceMetadata | UrlSourceMetadata,
    Field(discriminator="metadata_type"),
]


class SourceCreateResponse(PipelineSchema):
    source_id: NonEmptyStr
    status: SourceStatus
    message: str | None = None


class SourceDetailResponse(PipelineSchema):
    source_id: NonEmptyStr
    source_type: SourceType
    status: SourceStatus
    display_name: str | None = None
    current_stage: ProcessingStage
    input_uri: str | None = None
    source_uri: str | None = None
    canonical_uri: str | None = None
    created_at: datetime
    error: SourceError | None = None
    metadata: SourceMetadata | None = None
