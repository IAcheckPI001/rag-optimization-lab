class ExtractionError(Exception):
    error_code = "extraction_error"

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


class ExtractionParsingError(ExtractionError):
    error_code = "extraction_parsing_failed"


class ExtractionNoContentError(ExtractionError):
    error_code = "extraction_no_content"


class ExtractionSourceTypeMismatchError(ExtractionError):
    error_code = "extraction_source_type_mismatch"


class ExtractionInvariantError(ExtractionError):
    error_code = "extraction_invariant_failed"
