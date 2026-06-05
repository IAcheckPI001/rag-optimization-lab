from enum import Enum

from pydantic import BaseModel


class SourceType(str, Enum):
    pdf = "pdf"
    docx = "docx"
    url = "url"


class SourceStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class SourceCreateResponse(BaseModel):
    source_id: str
    status: SourceStatus
    message: str | None = None


class SourceDetailResponse(BaseModel):
    source_id: str
    source_type: SourceType
    status: SourceStatus
    source_uri: str | None = None
    original_filename: str | None = None
