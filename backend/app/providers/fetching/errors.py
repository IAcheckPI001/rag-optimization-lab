class UrlFetchError(Exception):
    error_code = "url_fetch_error"

    def __init__(
        self,
        message: str,
        *,
        error_code: str | None = None,
        retryable: bool = False,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if error_code is not None:
            self.error_code = error_code
        self.retryable = retryable
        self.details = details or {}


class UrlValidationError(UrlFetchError):
    error_code = "invalid_url"


class UrlSecurityError(UrlFetchError):
    error_code = "blocked_destination"


class UrlNetworkError(UrlFetchError):
    error_code = "network_error"


class UrlResponseError(UrlFetchError):
    error_code = "http_response_error"


class UrlContentTooLargeError(UrlFetchError):
    error_code = "response_too_large"
