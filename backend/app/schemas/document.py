from pydantic import BaseModel

from app.schemas.source import SourceType


class RawDocumentUnit(BaseModel):
    document_id: str
    source_id: str
    source_type: SourceType
    source_uri: str | None
    content: str
    page_number: int | None = None
    section: str | None = None
    metadata: dict[str, object]


class CleanDocumentUnit(BaseModel):
    document_id: str
    source_id: str
    source_type: SourceType
    source_uri: str | None
    content: str
    page_number: int | None = None
    section: str | None = None
    metadata: dict[str, object]


class DocumentChunk(BaseModel):
    chunk_id: str
    document_id: str
    source_id: str
    source_type: SourceType
    source_uri: str | None
    content: str
    chunk_index: int
    page_number: int | None = None
    section: str | None = None
    metadata: dict[str, object]
