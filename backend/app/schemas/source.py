from datetime import datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints


NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


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


class SourceError(BaseModel):
    error_code: NonEmptyStr
    message: NonEmptyStr
    failed_stage: ProcessingStage
    retryable: bool = False


class BaseFileMetadata(BaseModel):
    title: str | None = None
    original_filename: NonEmptyStr
    checksum_sha256: str | None = None


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


class UrlSourceMetadata(BaseModel):
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


SourceMetadata = Annotated[
    PdfSourceMetadata | DocxSourceMetadata | UrlSourceMetadata,
    Field(discriminator="metadata_type"),
]


class SourceCreateResponse(BaseModel):
    source_id: NonEmptyStr
    status: SourceStatus
    message: str | None = None


class SourceDetailResponse(BaseModel):
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
    original_filename: str | None = None
