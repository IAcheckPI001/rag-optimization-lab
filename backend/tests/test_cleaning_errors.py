from app.rag.cleaning.errors import (
    CleaningError,
    CleaningInputError,
    CleaningInvariantError,
    CleaningLimitError,
    CleaningNoContentError,
)


def test_cleaning_error_exposes_message_retryable_details_and_code() -> None:
    error = CleaningError(
        "Cleaning failed.",
        retryable=True,
        details={"rule": "normalize_whitespace"},
    )

    assert str(error) == "Cleaning failed."
    assert error.message == "Cleaning failed."
    assert error.retryable is True
    assert error.details == {"rule": "normalize_whitespace"}
    assert error.error_code == "cleaning_error"


def test_cleaning_error_defaults_details_to_empty_dict() -> None:
    error = CleaningError("Cleaning failed.")

    assert error.retryable is False
    assert error.details == {}


def test_cleaning_error_subclasses_use_stable_error_codes() -> None:
    assert CleaningInputError("bad input").error_code == "cleaning_input_error"
    assert CleaningNoContentError("empty").error_code == "cleaning_no_content"
    assert CleaningLimitError("too large").error_code == "cleaning_limit_exceeded"
    assert (
        CleaningInvariantError("broken invariant").error_code
        == "cleaning_invariant_failed"
    )
