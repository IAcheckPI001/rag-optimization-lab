

import pytest

from pydantic import ValidationError

from app.schemas.generation import Citation, QueryResponse
from app.schemas.retrieval import RetrievalMethod
from app.schemas.retrieval import QueryRequest
from app.schemas.source import SourceType


def test_query_request_accepts_valid_values() -> None:
    request = QueryRequest(
        question="What is retrieval-augmented generation?",
        top_k=5,
    )

    assert request.question == "What is retrieval-augmented generation?"
    assert request.top_k == 5


@pytest.mark.parametrize("question", ["", "   ", "\n"])
def test_query_request_rejects_blank_question(question: str) -> None:
    with pytest.raises(ValidationError, match="question must not be blank"):
        QueryRequest(
            question=question,
            top_k=5,
        )


@pytest.mark.parametrize("top_k", [0, -1, -5])
def test_query_request_rejects_non_positive_top_k(top_k: int) -> None:
    with pytest.raises(ValidationError):
        QueryRequest(
            question="What is RAG?",
            top_k=top_k,
        )


def test_citation_accepts_compact_fields() -> None:
    citation = Citation(
        label="[1]",
        chunk_id="chunk_001",
        quote="Leave policy allows 12 paid days.",
    )

    assert citation.label == "[1]"
    assert citation.chunk_id == "chunk_001"
    assert citation.quote == "Leave policy allows 12 paid days."


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("label", ""),
        ("label", "   "),
        ("chunk_id", ""),
        ("chunk_id", None),
        ("quote", ""),
        ("quote", "\n"),
    ],
)
def test_citation_rejects_empty_or_null_required_fields(
    field_name: str,
    field_value: object,
) -> None:
    payload = {
        "label": "[1]",
        "chunk_id": "chunk_001",
        "quote": "Leave policy allows 12 paid days.",
    }
    payload[field_name] = field_value

    with pytest.raises(ValidationError):
        Citation.model_validate(payload)


def test_citation_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Citation.model_validate(
            {
                "label": "[1]",
                "chunk_id": "chunk_001",
                "quote": "Leave policy allows 12 paid days.",
                "source_uri": "storage://sources/src_001/raw.pdf",
            }
        )


def retrieved_context_payload(
    *,
    chunk_id: str = "chunk_001",
    selected_for_generation: bool = True,
) -> dict[str, object]:
    return {
        "chunk": {
            "chunk_id": chunk_id,
            "clean_unit_id": "clean_001",
            "document_id": "doc_001",
            "source_id": "src_001",
            "content": "Leave policy allows 12 paid days for eligible employees.",
            "content_hash": "hash_001",
            "source_type": SourceType.pdf,
            "source_uri": "storage://sources/src_001/raw.pdf",
            "page_start": 2,
            "page_end": 2,
            "section": "Leave Policy",
            "heading_path": ["Employee Handbook", "Leave Policy"],
            "token_count": 12,
        },
        "retrieval_methods": [RetrievalMethod.vector],
        "vector_score": 0.91,
        "final_score": 0.91,
        "retrieval_rank": 1,
        "final_rank": 1,
        "selected_for_generation": selected_for_generation,
    }


def query_response_payload() -> dict[str, object]:
    return {
        "answer": "Eligible employees receive 12 paid days [1].",
        "citations": [
            {
                "label": "[1]",
                "chunk_id": "chunk_001",
                "quote": "Leave policy allows 12 paid days",
            }
        ],
        "contexts": [retrieved_context_payload()],
        "insufficient_context": False,
    }


def test_query_response_accepts_valid_citation_references() -> None:
    response = QueryResponse(**query_response_payload())

    assert response.citations[0].label == "[1]"
    assert response.citations[0].chunk_id == "chunk_001"
    assert response.contexts[0].selected_for_generation is True


def test_query_response_rejects_unknown_citation_chunk() -> None:
    payload = query_response_payload()
    payload["citations"][0]["chunk_id"] = "chunk_missing"

    with pytest.raises(
        ValidationError,
        match="citation references unknown chunk: chunk_missing",
    ):
        QueryResponse.model_validate(payload)


def test_query_response_rejects_citation_for_unselected_context() -> None:
    payload = query_response_payload()
    payload["contexts"] = [
        retrieved_context_payload(selected_for_generation=False)
    ]

    with pytest.raises(
        ValidationError,
        match="citation chunk was not selected for generation: chunk_001",
    ):
        QueryResponse.model_validate(payload)


def test_query_response_rejects_quote_not_contained_in_chunk() -> None:
    payload = query_response_payload()
    payload["citations"][0]["quote"] = "A sentence that is not in the chunk."

    with pytest.raises(
        ValidationError,
        match="citation quote is not contained in chunk: chunk_001",
    ):
        QueryResponse.model_validate(payload)


def test_query_response_rejects_label_missing_from_answer() -> None:
    payload = query_response_payload()
    payload["answer"] = "Eligible employees receive 12 paid days."

    with pytest.raises(
        ValidationError,
        match=r"citation label is missing from answer: \[1\]",
    ):
        QueryResponse.model_validate(payload)


def test_query_response_rejects_unknown_fields() -> None:
    payload = query_response_payload()
    payload["unexpected"] = "nope"

    with pytest.raises(ValidationError):
        QueryResponse.model_validate(payload)
