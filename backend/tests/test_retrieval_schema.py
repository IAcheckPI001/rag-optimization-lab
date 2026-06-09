import pytest
from pydantic import ValidationError

from app.schemas.retrieval import (
    RetrievalMethod,
    RetrievedChunkSnapshot,
    RetrievedContext,
)
from app.schemas.source import SourceType


def chunk_snapshot_payload() -> dict[str, object]:
    return {
        "chunk_id": "chunk_001",
        "clean_unit_id": "clean_001",
        "document_id": "doc_001",
        "source_id": "src_001",
        "content": "Leave policy allows 12 paid days.",
        "content_hash": "8f6c5f6c0bfb4e916ce8570d6e2c6c9a",
        "source_type": SourceType.pdf,
        "source_uri": "storage://sources/src_001/raw.pdf",
        "page_start": 2,
        "page_end": 3,
        "section": "Leave Policy",
        "heading_path": ["Employee Handbook", "Human Resources", "Leave Policy"],
        "token_count": 9,
        "extra_metadata": {"collection_name": "rag_chunks"},
    }


def retrieved_context_payload() -> dict[str, object]:
    return {
        "chunk": chunk_snapshot_payload(),
        "retrieval_methods": [RetrievalMethod.vector, RetrievalMethod.metadata],
        "vector_score": 0.87,
        "keyword_score": None,
        "metadata_boost": 0.1,
        "rerank_score": None,
        "final_score": 0.97,
        "retrieval_rank": 2,
        "final_rank": 1,
        "selected_for_generation": True,
    }


def test_retrieved_chunk_snapshot_accepts_valid_input() -> None:
    snapshot = RetrievedChunkSnapshot(**chunk_snapshot_payload())

    assert snapshot.chunk_id == "chunk_001"
    assert snapshot.clean_unit_id == "clean_001"
    assert snapshot.document_id == "doc_001"
    assert snapshot.source_id == "src_001"
    assert snapshot.source_type is SourceType.pdf
    assert snapshot.page_start == 2
    assert snapshot.page_end == 3
    assert snapshot.heading_path == [
        "Employee Handbook",
        "Human Resources",
        "Leave Policy",
    ]
    assert snapshot.extra_metadata == {"collection_name": "rag_chunks"}


def test_retrieved_context_accepts_valid_input() -> None:
    context = RetrievedContext(**retrieved_context_payload())

    assert context.chunk.chunk_id == "chunk_001"
    assert context.retrieval_methods == [
        RetrievalMethod.vector,
        RetrievalMethod.metadata,
    ]
    assert context.vector_score == 0.87
    assert context.metadata_boost == 0.1
    assert context.final_score == 0.97
    assert context.retrieval_rank == 2
    assert context.final_rank == 1
    assert context.selected_for_generation is True


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("chunk_id", ""),
        ("document_id", "   "),
        ("source_id", None),
        ("content", ""),
        ("content_hash", "   "),
    ],
)
def test_retrieved_chunk_snapshot_rejects_empty_or_null_required_fields(
    field_name: str,
    field_value: object,
) -> None:
    payload = chunk_snapshot_payload()
    payload[field_name] = field_value

    with pytest.raises(ValidationError):
        RetrievedChunkSnapshot.model_validate(payload)


def test_retrieved_chunk_snapshot_rejects_page_end_without_page_start() -> None:
    payload = chunk_snapshot_payload()
    payload["page_start"] = None
    payload["page_end"] = 3

    with pytest.raises(ValidationError, match="page_start is required"):
        RetrievedChunkSnapshot.model_validate(payload)


def test_retrieved_chunk_snapshot_rejects_page_start_without_page_end() -> None:
    payload = chunk_snapshot_payload()
    payload["page_start"] = 3
    payload["page_end"] = None

    with pytest.raises(ValidationError, match="page_end is required"):
        RetrievedChunkSnapshot.model_validate(payload)


def test_retrieved_chunk_snapshot_rejects_page_end_before_page_start() -> None:
    payload = chunk_snapshot_payload()
    payload["page_start"] = 4
    payload["page_end"] = 3

    with pytest.raises(
        ValidationError,
        match="page_end must be greater than or equal to page_start",
    ):
        RetrievedChunkSnapshot.model_validate(payload)


def test_retrieved_chunk_snapshot_rejects_blank_heading_path_items() -> None:
    payload = chunk_snapshot_payload()
    payload["heading_path"] = ["Employee Handbook", ""]

    with pytest.raises(ValidationError):
        RetrievedChunkSnapshot.model_validate(payload)


def test_retrieved_chunk_snapshot_rejects_negative_token_count() -> None:
    payload = chunk_snapshot_payload()
    payload["token_count"] = -1

    with pytest.raises(ValidationError):
        RetrievedChunkSnapshot.model_validate(payload)


def test_retrieved_chunk_snapshot_rejects_zero_token_count() -> None:
    payload = chunk_snapshot_payload()
    payload["token_count"] = 0

    with pytest.raises(ValidationError):
        RetrievedChunkSnapshot.model_validate(payload)


def test_retrieved_chunk_snapshot_accepts_missing_token_count() -> None:
    payload = chunk_snapshot_payload()
    payload["token_count"] = None

    snapshot = RetrievedChunkSnapshot.model_validate(payload)

    assert snapshot.token_count is None


def test_retrieved_chunk_snapshot_rejects_unknown_fields() -> None:
    payload = chunk_snapshot_payload()
    payload["unexpected"] = "nope"

    with pytest.raises(ValidationError):
        RetrievedChunkSnapshot.model_validate(payload)


def test_retrieved_context_rejects_empty_retrieval_methods() -> None:
    payload = retrieved_context_payload()
    payload["retrieval_methods"] = []

    with pytest.raises(ValidationError):
        RetrievedContext.model_validate(payload)


def test_retrieved_context_rejects_unknown_fields() -> None:
    payload = retrieved_context_payload()
    payload["unexpected"] = "nope"

    with pytest.raises(ValidationError):
        RetrievedContext.model_validate(payload)


def test_retrieved_context_rejects_invalid_retrieval_method() -> None:
    payload = retrieved_context_payload()
    payload["retrieval_methods"] = ["semantic"]

    with pytest.raises(ValidationError):
        RetrievedContext.model_validate(payload)


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("retrieval_rank", 0),
        ("final_rank", 0),
    ],
)
def test_retrieved_context_rejects_invalid_ranks(
    field_name: str,
    field_value: int,
) -> None:
    payload = retrieved_context_payload()
    payload[field_name] = field_value

    with pytest.raises(ValidationError):
        RetrievedContext.model_validate(payload)
