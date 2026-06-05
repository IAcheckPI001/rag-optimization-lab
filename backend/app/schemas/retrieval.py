from pydantic import BaseModel, Field, field_validator

from app.schemas.source import SourceType


class RetrievedContext(BaseModel):
    chunk_id: str
    document_id: str
    content: str
    score: float
    rank: int
    retrieval_method: str
    source_type: SourceType
    source_uri: str | None
    page_number: int | None = None
    section: str | None = None
    metadata: dict[str, object]


class QueryRequest(BaseModel):
    question: str
    top_k: int = Field(default=5, gt=0)

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value
