
import pytest
from pydantic import ValidationError

from app.schemas.retrieval import (
    QueryRequest,
)

def test_query_request_accepts_valid_input() -> None:
    request = QueryRequest(
        question="What is the leave policy?",
        top_k=5,
    )

    assert request.question == "What is the leave policy?"
    assert request.top_k == 5

def test_query_request_strips_question() -> None:
    request = QueryRequest(
        question="  What is the leave policy?  ",
    )

    assert request.question == "What is the leave policy?"

@pytest.mark.parametrize(
    "question",
    ["", " ", "\n", "\t", " \n\t "],
)
def test_query_request_rejects_blank_question(
    question: str,
) -> None:
    with pytest.raises(
        ValidationError,
        match="question must not be blank",
    ):
        QueryRequest(question=question)

def test_query_request_rejects_question_over_limit() -> None:
    with pytest.raises(ValidationError):
        QueryRequest(question="a" * 3001)


def test_query_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        QueryRequest(
            question="What is the leave policy?",
            unexpected="nope",
        )

