from pydantic import BaseModel

from app.schemas.retrieval import RetrievedContext


class Citation(BaseModel):
    chunk_id: str
    document_id: str
    source_uri: str | None
    page_number: int | None = None
    section: str | None = None
    label: str | None = None


class QueryResponse(BaseModel):
    answer: str
    citations: list[Citation]
    contexts: list[RetrievedContext]
    insufficient_context: bool
