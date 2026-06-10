import pytest

from app.providers.extraction.errors import (
    ExtractionError,
    ExtractionInvariantError,
    ExtractionNoContentError,
    ExtractionParsingError,
    ExtractionSourceTypeMismatchError,
)


def test_extraction_error_preserves_message_retryable_and_details() -> None:
    error = ExtractionError(
        "Extraction failed.",
        retryable=True,
        details={"source_type": "pdf"},
    )

    assert error.error_code == "extraction_error"
    assert error.message == "Extraction failed."
    assert str(error) == "Extraction failed."
    assert error.retryable is True
    assert error.details == {"source_type": "pdf"}


@pytest.mark.parametrize(
    ("error_type", "error_code"),
    [
        (ExtractionParsingError, "extraction_parsing_failed"),
        (ExtractionNoContentError, "extraction_no_content"),
        (ExtractionSourceTypeMismatchError, "extraction_source_type_mismatch"),
        (ExtractionInvariantError, "extraction_invariant_failed"),
    ],
)
def test_extraction_error_subclasses_have_stable_error_codes(
    error_type: type[ExtractionError],
    error_code: str,
) -> None:
    error = error_type("Specific extraction failure.")

    assert isinstance(error, ExtractionError)
    assert error.error_code == error_code
    assert error.message == "Specific extraction failure."
    assert error.retryable is False
    assert error.details == {}


def test_error_details_do_not_require_or_expose_binary_content() -> None:
    error = ExtractionNoContentError(
        "No extractable content.",
        details={"document_id": "doc_001"},
    )

    assert error.details == {"document_id": "doc_001"}
    assert "content_bytes" not in error.details
