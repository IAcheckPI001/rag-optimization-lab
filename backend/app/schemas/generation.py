from pydantic import model_validator

from app.schemas.common import NonEmptyStr, PipelineSchema
from app.schemas.retrieval import RetrievedContext


class Citation(PipelineSchema):
    label: NonEmptyStr
    chunk_id: NonEmptyStr
    quote: NonEmptyStr


class QueryResponse(PipelineSchema):
    answer: str
    citations: list[Citation]
    contexts: list[RetrievedContext]
    insufficient_context: bool

    @model_validator(mode="after")
    def validate_citation_references(self) -> "QueryResponse":
        contexts_by_chunk_id = {
            context.chunk.chunk_id: context
            for context in self.contexts
        }

        for citation in self.citations:
            context = contexts_by_chunk_id.get(citation.chunk_id)

            if context is None:
                raise ValueError(
                    f"citation references unknown chunk: {citation.chunk_id}"
                )

            if not context.selected_for_generation:
                raise ValueError(
                    "citation chunk was not selected for generation: "
                    f"{citation.chunk_id}"
                )

            if citation.quote not in context.chunk.content:
                raise ValueError(
                    f"citation quote is not contained in chunk: {citation.chunk_id}"
                )

            if citation.label not in self.answer:
                raise ValueError(
                    f"citation label is missing from answer: {citation.label}"
                )

        return self
