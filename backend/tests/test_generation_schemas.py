

import pytest

from pydantic import ValidationError

from app.schemas.retrieval import QueryRequest

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