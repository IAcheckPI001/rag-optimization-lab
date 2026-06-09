from enum import Enum

from pydantic import Field, field_validator, model_validator

from app.schemas.common import NonEmptyStr, PipelineSchema
from app.schemas.source import SourceType


class RetrievalMethod(str, Enum):
    vector = "vector"
    keyword = "keyword"
    metadata = "metadata"
    rerank = "rerank"


class RetrievedChunkSnapshot(PipelineSchema):
    chunk_id: NonEmptyStr
    clean_unit_id: NonEmptyStr | None = None
    document_id: NonEmptyStr
    source_id: NonEmptyStr
    content: NonEmptyStr
    content_hash: NonEmptyStr
    source_type: SourceType
    source_uri: str | None = None
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    section: str | None = None
    heading_path: list[NonEmptyStr] = Field(default_factory=list)
    token_count: int | None = Field(default=None, ge=1)
    extra_metadata: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_page_range(self) -> "RetrievedChunkSnapshot":
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


class RetrievedContext(PipelineSchema):
    chunk: RetrievedChunkSnapshot
    retrieval_methods: list[RetrievalMethod] = Field(min_length=1)
    vector_score: float | None = None
    keyword_score: float | None = None
    metadata_boost: float | None = None
    rerank_score: float | None = None
    final_score: float
    retrieval_rank: int = Field(ge=1)
    final_rank: int | None = Field(default=None, ge=1)
    selected_for_generation: bool = False


class QueryRequest(PipelineSchema):
    question: str = Field(max_length=3000)
    top_k: int = Field(default=5, ge=1, le=20)

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value.strip()
