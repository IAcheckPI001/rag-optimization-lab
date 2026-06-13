from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from email.message import Message
from time import monotonic
from typing import Callable

import httpx

from app.providers.fetching.errors import (
    UrlContentTooLargeError,
    UrlFetchError,
    UrlNetworkError,
    UrlResponseError,
    UrlSecurityError,
)
from app.providers.fetching.url_security import (
    NormalizedUrl,
    Resolver,
    normalize_url,
    validate_destination,
)
from app.schemas.extraction import FetchedContent


REDIRECT_STATUSES = {301, 302, 303, 307, 308}
SUPPORTED_MEDIA_TYPES = {"text/html", "application/xhtml+xml"}


@dataclass(frozen=True)
class FetchPolicy:
    max_redirects: int = 5
    max_decoded_response_bytes: int = 5 * 1024 * 1024
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 10.0
    write_timeout_seconds: float = 5.0
    pool_timeout_seconds: float = 5.0
    total_fetch_deadline_seconds: float = 30.0
    user_agent: str = "rag-optimization-lab-url-fetcher/0.1"

    def timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self.connect_timeout_seconds,
            read=self.read_timeout_seconds,
            write=self.write_timeout_seconds,
            pool=self.pool_timeout_seconds,
        )


class HttpxUrlFetcher:
    def __init__(
        self,
        *,
        policy: FetchPolicy | None = None,
        resolver: Resolver | None = None,
        client: httpx.Client | None = None,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.policy = policy or FetchPolicy()
        self.resolver = resolver
        self.client = client
        self.transport = transport
        self.clock = clock

    def fetch(self, url: str) -> FetchedContent:
        started_at = self.clock()
        original = normalize_url(url)
        current = original
        visited = {current.request_url}
        redirect_count = 0

        context = (
            nullcontext(self.client)
            if self.client is not None
            else httpx.Client(
                follow_redirects=False,
                verify=True,
                trust_env=False,
                timeout=self.policy.timeout(),
                transport=self.transport or httpx.HTTPTransport(retries=0),
            )
        )

        with context as client:
            if client is None:
                raise UrlFetchError("HTTP client is unavailable.")

            while True:
                self._check_deadline(started_at, current)
                self._validate_destination(current)

                try:
                    with client.stream(
                        "GET",
                        current.request_url,
                        headers=self._headers(),
                        timeout=self._timeout_for_remaining_budget(
                            started_at, current
                        ),
                    ) as response:
                        self._check_deadline(started_at, current)
                        if response.status_code in REDIRECT_STATUSES:
                            redirect_count += 1
                            current = self._next_redirect_url(
                                current=current,
                                response=response,
                                visited=visited,
                                redirect_count=redirect_count,
                            )
                            continue

                        return self._build_fetched_content(
                            original_url=original.request_url,
                            current_url=current,
                            response=response,
                            redirect_count=redirect_count,
                            started_at=started_at,
                        )
                except UrlFetchError:
                    raise
                except httpx.TimeoutException as exc:
                    raise UrlNetworkError(
                        "URL request timed out.",
                        error_code="request_timeout",
                        retryable=True,
                        details={"url": current.diagnostic_url},
                    ) from exc
                except httpx.HTTPError as exc:
                    raise UrlNetworkError(
                        "URL request failed.",
                        error_code="network_error",
                        retryable=True,
                        details={"url": current.diagnostic_url},
                    ) from exc

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.policy.user_agent,
            "Accept": "text/html, application/xhtml+xml",
            "Accept-Encoding": "identity",
        }

    def _validate_destination(self, normalized_url: NormalizedUrl) -> None:
        if self.resolver is None:
            validate_destination(normalized_url)
            return
        validate_destination(normalized_url, resolver=self.resolver)

    def _next_redirect_url(
        self,
        *,
        current: NormalizedUrl,
        response: httpx.Response,
        visited: set[str],
        redirect_count: int,
    ) -> NormalizedUrl:
        if redirect_count > self.policy.max_redirects:
            raise UrlResponseError(
                "Redirect limit exceeded.",
                error_code="redirect_limit_exceeded",
                details={"url": current.diagnostic_url},
            )

        location = response.headers.get("Location")
        if location is None or not location.strip():
            raise UrlResponseError(
                "Redirect response is missing Location.",
                error_code="invalid_redirect",
                details={"url": current.diagnostic_url},
            )

        target = normalize_url(location, base_url=current.request_url)
        if current.scheme == "https" and target.scheme == "http":
            raise UrlSecurityError(
                "HTTPS to HTTP redirects are not allowed.",
                error_code="https_downgrade_redirect",
                details={
                    "url": current.diagnostic_url,
                    "redirect_url": target.diagnostic_url,
                },
            )

        self._validate_destination(target)

        if target.request_url in visited:
            raise UrlResponseError(
                "Redirect loop detected.",
                error_code="redirect_loop",
                details={"url": target.diagnostic_url},
            )
        visited.add(target.request_url)

        return target

    def _build_fetched_content(
        self,
        *,
        original_url: str,
        current_url: NormalizedUrl,
        response: httpx.Response,
        redirect_count: int,
        started_at: float,
    ) -> FetchedContent:
        self._validate_status(response, current_url)
        content_length_header = self._validate_content_length(response, current_url)
        media_type, charset = self._parse_content_type(response, current_url)
        content = self._read_bounded_content(response, current_url, started_at)

        if not content:
            raise UrlResponseError(
                "URL response body is empty.",
                error_code="empty_response",
                details={"url": current_url.diagnostic_url},
            )

        return FetchedContent(
            original_url=original_url,
            final_url=current_url.request_url,
            content_bytes=content,
            media_type=media_type,
            charset=charset,
            status_code=response.status_code,
            redirect_count=redirect_count,
            extra_metadata={
                "downloaded_bytes": len(content),
                "content_length_header": content_length_header,
            },
        )

    def _validate_status(self, response: httpx.Response, url: NormalizedUrl) -> None:
        status = response.status_code
        if status in {204, 205}:
            raise UrlResponseError(
                "URL response has no content.",
                error_code="empty_response",
                details={"url": url.diagnostic_url, "status_code": status},
            )
        if status == 206:
            raise UrlResponseError(
                "Partial content responses are not supported.",
                error_code="http_status_error",
                details={"url": url.diagnostic_url, "status_code": status},
            )
        if status == 304 or 300 <= status < 400:
            raise UrlResponseError(
                "Unexpected redirect response.",
                error_code="http_status_error",
                details={"url": url.diagnostic_url, "status_code": status},
            )
        if status < 200 or status >= 300:
            raise UrlResponseError(
                "URL response status is not successful.",
                error_code="http_status_error",
                details={"url": url.diagnostic_url, "status_code": status},
            )

    def _validate_content_length(
        self, response: httpx.Response, url: NormalizedUrl
    ) -> int | None:
        values = _header_values(response, "Content-Length")
        if not values:
            return None
        if len(set(values)) != 1:
            raise UrlResponseError(
                "Conflicting Content-Length headers.",
                error_code="invalid_content_length",
                details={"url": url.diagnostic_url},
            )

        try:
            content_length = int(values[0])
        except ValueError as exc:
            raise UrlResponseError(
                "Content-Length header is invalid.",
                error_code="invalid_content_length",
                details={"url": url.diagnostic_url},
            ) from exc

        if content_length < 0:
            raise UrlResponseError(
                "Content-Length header is negative.",
                error_code="invalid_content_length",
                details={"url": url.diagnostic_url},
            )
        if content_length > self.policy.max_decoded_response_bytes:
            raise UrlContentTooLargeError(
                "URL response is too large.",
                error_code="response_too_large",
                details={
                    "url": url.diagnostic_url,
                    "content_length_header": content_length,
                    "max_decoded_response_bytes": self.policy.max_decoded_response_bytes,
                },
            )
        return content_length

    def _parse_content_type(
        self, response: httpx.Response, url: NormalizedUrl
    ) -> tuple[str, str | None]:
        values = _header_values(response, "Content-Type")
        if not values:
            raise UrlResponseError(
                "Content-Type header is required.",
                error_code="unsupported_content_type",
                details={"url": url.diagnostic_url},
            )
        if len(set(values)) != 1:
            raise UrlResponseError(
                "Conflicting Content-Type headers.",
                error_code="malformed_content_type",
                details={"url": url.diagnostic_url},
            )

        message = Message()
        message["content-type"] = values[0]
        media_type = message.get_content_type().lower()
        if media_type not in SUPPORTED_MEDIA_TYPES:
            raise UrlResponseError(
                "Content-Type is not supported.",
                error_code="unsupported_content_type",
                details={"url": url.diagnostic_url, "media_type": media_type},
            )

        charset = message.get_param("charset", header="content-type")
        if charset is not None:
            charset = charset.strip() or None
        return media_type, charset

    def _read_bounded_content(
        self, response: httpx.Response, url: NormalizedUrl, started_at: float
    ) -> bytes:
        chunks: list[bytes] = []
        downloaded = 0
        for chunk in response.iter_bytes():
            self._check_deadline(started_at, url)
            if not chunk:
                continue
            downloaded += len(chunk)
            if downloaded > self.policy.max_decoded_response_bytes:
                raise UrlContentTooLargeError(
                    "URL response is too large.",
                    error_code="response_too_large",
                    details={
                        "url": url.diagnostic_url,
                        "downloaded_bytes": downloaded,
                        "max_decoded_response_bytes": self.policy.max_decoded_response_bytes,
                    },
                )
            chunks.append(chunk)
        self._check_deadline(started_at, url)
        return b"".join(chunks)

    def _check_deadline(self, started_at: float, url: NormalizedUrl) -> None:
        if self.clock() - started_at > self.policy.total_fetch_deadline_seconds:
            raise UrlNetworkError(
                "URL fetch deadline exceeded.",
                error_code="request_deadline_exceeded",
                retryable=True,
                details={"url": url.diagnostic_url},
            )

    def _timeout_for_remaining_budget(
        self, started_at: float, url: NormalizedUrl
    ) -> httpx.Timeout:
        remaining = self.policy.total_fetch_deadline_seconds - (
            self.clock() - started_at
        )
        if remaining <= 0:
            raise UrlNetworkError(
                "URL fetch deadline exceeded.",
                error_code="request_deadline_exceeded",
                retryable=True,
                details={"url": url.diagnostic_url},
            )

        return httpx.Timeout(
            connect=min(self.policy.connect_timeout_seconds, remaining),
            read=min(self.policy.read_timeout_seconds, remaining),
            write=min(self.policy.write_timeout_seconds, remaining),
            pool=min(self.policy.pool_timeout_seconds, remaining),
        )


def _header_values(response: httpx.Response, header_name: str) -> list[str]:
    values = response.headers.get_list(header_name)
    if len(values) == 1 and "," in values[0]:
        return [value.strip() for value in values[0].split(",") if value.strip()]
    return [value.strip() for value in values if value.strip()]
