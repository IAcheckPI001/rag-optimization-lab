class CleaningError(Exception):
    error_code = "cleaning_error"

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.retryable = retryable
        self.details = details or {}


class CleaningInputError(CleaningError):
    error_code = "cleaning_input_error"


class CleaningNoContentError(CleaningError):
    error_code = "cleaning_no_content"


class CleaningLimitError(CleaningError):
    error_code = "cleaning_limit_exceeded"


class CleaningInvariantError(CleaningError):
    error_code = "cleaning_invariant_failed"
