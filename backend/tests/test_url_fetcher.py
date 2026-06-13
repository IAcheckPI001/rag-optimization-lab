import httpx
import pytest

from app.providers.fetching.errors import (
    UrlContentTooLargeError,
    UrlNetworkError,
    UrlResponseError,
    UrlSecurityError,
    UrlValidationError,
)
from app.providers.fetching.httpx_url_fetcher import FetchPolicy, HttpxUrlFetcher
from app.providers.fetching.url_security import (
    normalize_url,
    sanitize_url_for_diagnostics,
    validate_destination,
    validate_public_ip,
)
from app.schemas.extraction import FetchedContent


PUBLIC_IP = "93.184.216.34"


class ClosingTransport(httpx.BaseTransport):
    def __init__(self) -> None:
        self.closed = False

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return html_response(b"<html>ok</html>")

    def close(self) -> None:
        self.closed = True


class TrackingStream(httpx.SyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks
        self.closed = False

    def __iter__(self):
        yield from self.chunks

    def close(self) -> None:
        self.closed = True


def public_resolver(hostname: str) -> list[str]:
    return [PUBLIC_IP]


def private_resolver(hostname: str) -> list[str]:
    return ["10.0.0.1"]


def mixed_resolver(hostname: str) -> list[str]:
    return [PUBLIC_IP, "10.0.0.1"]


def fetcher_for(
    handler,
    *,
    resolver=public_resolver,
    policy: FetchPolicy | None = None,
    clock=None,
) -> HttpxUrlFetcher:
    return HttpxUrlFetcher(
        resolver=resolver,
        transport=httpx.MockTransport(handler),
        policy=policy,
        clock=clock or __import__("time").monotonic,
    )


def html_response(
    content: bytes = b"<html>Hello</html>",
    *,
    status_code: int = 200,
    headers: dict[str, str] | list[tuple[str, str]] | None = None,
) -> httpx.Response:
    response_headers: dict[str, str] | list[tuple[str, str]] = headers or {
        "Content-Type": "text/html; charset=utf-8"
    }
    return httpx.Response(status_code, headers=response_headers, content=content)


def test_url_normalization_preserves_query_and_strips_fragment() -> None:
    normalized = normalize_url("HTTP://ExAmPle.COM./path?a=1#section")

    assert normalized.request_url == "http://example.com/path?a=1"
    assert normalized.diagnostic_url == "http://example.com/path"
    assert normalized.scheme == "http"
    assert normalized.hostname == "example.com"
    assert normalized.port == 80


def test_url_normalization_converts_idna_hostname() -> None:
    normalized = normalize_url("https://éxample.com/")

    assert normalized.hostname == "xn--xample-9ua.com"
    assert normalized.request_url == "https://xn--xample-9ua.com/"


@pytest.mark.parametrize(
    "url, error_code",
    [
        ("", "invalid_url"),
        ("/relative", "invalid_url"),
        ("file:///tmp/a.html", "unsupported_scheme"),
        ("ftp://example.com/", "unsupported_scheme"),
        ("javascript:alert(1)", "unsupported_scheme"),
        ("https://user:pass@example.com/", "userinfo_not_allowed"),
        ("http://example.com:81/", "disallowed_port"),
        ("https://example.com:444/", "disallowed_port"),
        ("http://exa mple.com/", "invalid_url"),
    ],
)
def test_url_validation_rejects_invalid_inputs(url: str, error_code: str) -> None:
    with pytest.raises(UrlValidationError) as exc_info:
        normalize_url(url)

    assert exc_info.value.error_code == error_code


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "http://api.localhost/",
    ],
)
def test_security_rejects_localhost_names(url: str) -> None:
    with pytest.raises(UrlSecurityError):
        normalize_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://169.254.169.254/",
    ],
)
def test_security_rejects_private_ip_literals(url: str) -> None:
    normalized = normalize_url(url)

    with pytest.raises(UrlSecurityError):
        validate_destination(normalized, resolver=public_resolver)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "::1",
        "10.0.0.1",
        "fc00::1",
        "169.254.1.1",
        "169.254.169.254",
        "100.64.0.1",
        "224.0.0.1",
        "0.0.0.0",
    ],
)
def test_ip_validation_rejects_non_public_addresses(address: str) -> None:
    with pytest.raises(UrlSecurityError):
        validate_public_ip(address, diagnostic_url="http://example.com/")


def test_dns_mixed_public_private_results_are_rejected() -> None:
    normalized = normalize_url("https://example.com/")

    with pytest.raises(UrlSecurityError):
        validate_destination(normalized, resolver=mixed_resolver)


def test_dns_failure_is_network_error() -> None:
    def failing_resolver(hostname: str) -> list[str]:
        raise OSError("dns down")

    normalized = normalize_url("https://example.com/")

    with pytest.raises(UrlNetworkError) as exc_info:
        validate_destination(normalized, resolver=failing_resolver)

    assert exc_info.value.error_code == "dns_resolution_failed"


def test_fetcher_returns_fetched_content_for_valid_html() -> None:
    seen_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return html_response(
            b"<html>M\xe1\xbb\xa5c l\xe1\xbb\xa5c</html>",
            headers={
                "Content-Type": "text/html; charset=utf-8",
                "Content-Length": "23",
            },
        )

    result = fetcher_for(handler).fetch("https://example.com/page?token=secret#frag")

    assert isinstance(result, FetchedContent)
    assert result.original_url == "https://example.com/page?token=secret"
    assert result.final_url == "https://example.com/page?token=secret"
    assert result.content_bytes == b"<html>M\xe1\xbb\xa5c l\xe1\xbb\xa5c</html>"
    assert result.media_type == "text/html"
    assert result.charset == "utf-8"
    assert result.status_code == 200
    assert result.redirect_count == 0
    assert result.extra_metadata["downloaded_bytes"] == len(result.content_bytes)
    assert result.extra_metadata["content_length_header"] == 23
    assert "content_bytes" not in result.model_dump()
    assert "content_bytes" not in repr(result)
    assert seen_requests[0].headers["accept-encoding"] == "identity"
    assert "cookie" not in seen_requests[0].headers
    assert "authorization" not in seen_requests[0].headers


def test_fetcher_supports_xhtml_content_type() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return html_response(
            b"<html/>",
            headers={"Content-Type": "application/xhtml+xml"},
        )

    result = fetcher_for(handler).fetch("https://example.com/")

    assert result.media_type == "application/xhtml+xml"


def test_redirect_relative_url_is_revalidated_and_counted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "http://example.com/start":
            return httpx.Response(302, headers={"Location": "/final#ignored"})
        return html_response(b"<html>Final</html>")

    result = fetcher_for(handler).fetch("http://example.com/start")

    assert result.final_url == "http://example.com/final"
    assert result.redirect_count == 1


def test_https_to_http_redirect_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "http://example.com/"})

    with pytest.raises(UrlSecurityError) as exc_info:
        fetcher_for(handler).fetch("https://example.com/")

    assert exc_info.value.error_code == "https_downgrade_redirect"


def test_redirect_to_private_destination_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "http://10.0.0.1/"})

    with pytest.raises(UrlSecurityError):
        fetcher_for(handler).fetch("http://example.com/")


def test_redirect_loop_uses_normalized_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "HTTP://EXAMPLE.COM./#x"})

    with pytest.raises(UrlResponseError) as exc_info:
        fetcher_for(handler).fetch("http://example.com/")

    assert exc_info.value.error_code == "redirect_loop"


def test_redirect_limit_is_enforced() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "/next"})

    with pytest.raises(UrlResponseError) as exc_info:
        fetcher_for(handler, policy=FetchPolicy(max_redirects=0)).fetch(
            "http://example.com/"
        )

    assert exc_info.value.error_code == "redirect_limit_exceeded"


def test_missing_redirect_location_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302)

    with pytest.raises(UrlResponseError) as exc_info:
        fetcher_for(handler).fetch("http://example.com/")

    assert exc_info.value.error_code == "invalid_redirect"


@pytest.mark.parametrize("status_code", [204, 205])
def test_empty_success_statuses_are_rejected(status_code: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return html_response(b"", status_code=status_code)

    with pytest.raises(UrlResponseError) as exc_info:
        fetcher_for(handler).fetch("http://example.com/")

    assert exc_info.value.error_code == "empty_response"


@pytest.mark.parametrize("status_code", [206, 304, 400, 500])
def test_unsupported_final_statuses_are_rejected(status_code: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return html_response(b"<html/>", status_code=status_code)

    with pytest.raises(UrlResponseError) as exc_info:
        fetcher_for(handler).fetch("http://example.com/")

    assert exc_info.value.error_code == "http_status_error"


@pytest.mark.parametrize(
    "headers, error_code",
    [
        ({}, "unsupported_content_type"),
        ({"Content-Type": "text/plain"}, "unsupported_content_type"),
        ({"Content-Type": "text/html, application/json"}, "malformed_content_type"),
    ],
)
def test_content_type_validation(headers: dict[str, str], error_code: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers=headers, content=b"<html/>")

    with pytest.raises(UrlResponseError) as exc_info:
        fetcher_for(handler).fetch("http://example.com/")

    assert exc_info.value.error_code == error_code


@pytest.mark.parametrize("content_length", ["abc", "-1", "2, 3"])
def test_invalid_content_length_is_rejected(content_length: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return html_response(
            b"<html/>",
            headers={
                "Content-Type": "text/html",
                "Content-Length": content_length,
            },
        )

    with pytest.raises(UrlResponseError) as exc_info:
        fetcher_for(handler).fetch("http://example.com/")

    assert exc_info.value.error_code == "invalid_content_length"


def test_content_length_over_limit_is_rejected_early() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return html_response(
            b"<html/>",
            headers={"Content-Type": "text/html", "Content-Length": "10"},
        )

    with pytest.raises(UrlContentTooLargeError) as exc_info:
        fetcher_for(
            handler,
            policy=FetchPolicy(max_decoded_response_bytes=5),
        ).fetch("http://example.com/")

    assert exc_info.value.error_code == "response_too_large"


def test_streamed_body_over_limit_is_rejected_without_partial_result() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return html_response(b"123456", headers={"Content-Type": "text/html"})

    with pytest.raises(UrlContentTooLargeError) as exc_info:
        fetcher_for(
            handler,
            policy=FetchPolicy(max_decoded_response_bytes=5),
        ).fetch("http://example.com/")

    assert exc_info.value.error_code == "response_too_large"


def test_body_exactly_at_limit_is_accepted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return html_response(b"12345", headers={"Content-Type": "text/html"})

    result = fetcher_for(
        handler,
        policy=FetchPolicy(max_decoded_response_bytes=5),
    ).fetch("http://example.com/")

    assert result.content_bytes == b"12345"


def test_empty_body_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return html_response(b"")

    with pytest.raises(UrlResponseError) as exc_info:
        fetcher_for(handler).fetch("http://example.com/")

    assert exc_info.value.error_code == "empty_response"


def test_network_timeout_is_mapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(UrlNetworkError) as exc_info:
        fetcher_for(handler).fetch("http://example.com/")

    assert exc_info.value.error_code == "request_timeout"


def test_per_hop_timeout_is_capped_by_remaining_deadline() -> None:
    seen_timeout: dict[str, float] = {}
    times = iter([0.0, 1.0, 2.0])

    def clock() -> float:
        return next(times, 2.0)

    def handler(request: httpx.Request) -> httpx.Response:
        seen_timeout.update(request.extensions["timeout"])
        return html_response(b"<html/>")

    result = fetcher_for(
        handler,
        policy=FetchPolicy(
            connect_timeout_seconds=10,
            read_timeout_seconds=10,
            write_timeout_seconds=10,
            pool_timeout_seconds=10,
            total_fetch_deadline_seconds=5,
        ),
        clock=clock,
    ).fetch("http://example.com/")

    assert result.content_bytes == b"<html/>"
    assert seen_timeout == {
        "connect": 3.0,
        "read": 3.0,
        "write": 3.0,
        "pool": 3.0,
    }


def test_total_fetch_deadline_is_enforced() -> None:
    times = iter([0.0, 31.0])

    def clock() -> float:
        return next(times)

    def handler(request: httpx.Request) -> httpx.Response:
        return html_response(b"<html/>")

    with pytest.raises(UrlNetworkError) as exc_info:
        fetcher_for(handler, clock=clock).fetch("http://example.com/")

    assert exc_info.value.error_code == "request_deadline_exceeded"


def test_no_automatic_retries() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return html_response(b"<html/>", status_code=500)

    with pytest.raises(UrlResponseError):
        fetcher_for(handler).fetch("http://example.com/")

    assert calls == 1


def test_owned_client_closes_owned_transport_after_fetch() -> None:
    transport = ClosingTransport()

    result = HttpxUrlFetcher(
        resolver=public_resolver,
        transport=transport,
    ).fetch("http://example.com/")

    assert result.content_bytes == b"<html>ok</html>"
    assert transport.closed is True


def test_injected_client_is_not_closed_by_fetcher() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return html_response(b"<html/>")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        result = HttpxUrlFetcher(
            resolver=public_resolver,
            client=client,
        ).fetch("http://example.com/")

        assert result.content_bytes == b"<html/>"
        assert client.is_closed is False
    finally:
        client.close()


def test_response_stream_is_closed_after_over_limit_error() -> None:
    stream = TrackingStream([b"123456"])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            stream=stream,
        )

    with pytest.raises(UrlContentTooLargeError):
        fetcher_for(
            handler,
            policy=FetchPolicy(max_decoded_response_bytes=5),
        ).fetch("http://example.com/")

    assert stream.closed is True


def test_safe_diagnostic_url_excludes_sensitive_parts() -> None:
    assert (
        sanitize_url_for_diagnostics(
            "https://user:pass@example.com/page?token=secret#section"
        )
        == "https://example.com/page"
    )


def test_error_details_use_sanitized_urls() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return html_response(b"<html/>", status_code=500)

    with pytest.raises(UrlResponseError) as exc_info:
        fetcher_for(handler).fetch("https://example.com/page?token=secret#frag")

    assert exc_info.value.details["url"] == "https://example.com/page"
    assert "token" not in str(exc_info.value.details)


def test_duplicate_content_length_headers_are_rejected_when_observable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return html_response(
            b"<html/>",
            headers=[
                ("Content-Type", "text/html"),
                ("Content-Length", "2"),
                ("Content-Length", "3"),
            ],
        )

    with pytest.raises(UrlResponseError) as exc_info:
        fetcher_for(handler).fetch("http://example.com/")

    assert exc_info.value.error_code == "invalid_content_length"


def test_duplicate_content_type_headers_are_rejected_when_observable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return html_response(
            b"<html/>",
            headers=[
                ("Content-Type", "text/html"),
                ("Content-Type", "application/xhtml+xml"),
            ],
        )

    with pytest.raises(UrlResponseError) as exc_info:
        fetcher_for(handler).fetch("http://example.com/")

    assert exc_info.value.error_code == "malformed_content_type"
