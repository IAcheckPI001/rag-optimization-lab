from __future__ import annotations

from dataclasses import dataclass
import ipaddress
from socket import gaierror, getaddrinfo
from typing import Callable
from urllib.parse import SplitResult, urljoin, urlsplit, urlunsplit

from app.providers.fetching.errors import (
    UrlNetworkError,
    UrlSecurityError,
    UrlValidationError,
)


Resolver = Callable[[str], list[str]]

ALLOWED_SCHEMES = {"http", "https"}
METADATA_IPS = {ipaddress.ip_address("169.254.169.254")}
SHARED_ADDRESS_SPACE = ipaddress.ip_network("100.64.0.0/10")


@dataclass(frozen=True)
class NormalizedUrl:
    original_url: str
    request_url: str
    diagnostic_url: str
    scheme: str
    hostname: str
    port: int
    is_ip_literal: bool


def default_resolver(hostname: str) -> list[str]:
    try:
        infos = getaddrinfo(hostname, None)
    except gaierror as exc:
        raise UrlNetworkError(
            "DNS resolution failed.",
            error_code="dns_resolution_failed",
            retryable=True,
            details={"url": sanitize_url_for_diagnostics(f"https://{hostname}/")},
        ) from exc

    addresses = sorted({info[4][0] for info in infos})
    if not addresses:
        raise UrlNetworkError(
            "DNS resolution returned no addresses.",
            error_code="dns_resolution_failed",
            retryable=True,
            details={"url": sanitize_url_for_diagnostics(f"https://{hostname}/")},
        )
    return addresses


def normalize_url(url: str, *, base_url: str | None = None) -> NormalizedUrl:
    if not isinstance(url, str) or not url.strip():
        raise UrlValidationError("URL must not be blank.", error_code="invalid_url")

    if _has_control_or_whitespace(url):
        raise UrlValidationError(
            "URL contains control characters or whitespace.",
            error_code="invalid_url",
        )

    candidate = urljoin(base_url, url) if base_url is not None else url
    split = urlsplit(candidate)

    if not split.scheme:
        raise UrlValidationError("URL must be absolute.", error_code="invalid_url")

    scheme = split.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise UrlValidationError(
            "URL scheme is not supported.",
            error_code="unsupported_scheme",
            details={"scheme": scheme},
        )

    if not split.netloc or split.hostname is None:
        raise UrlValidationError("URL hostname is required.", error_code="invalid_url")

    if split.username is not None or split.password is not None:
        raise UrlValidationError(
            "URL credentials are not allowed.",
            error_code="userinfo_not_allowed",
            details={"url": _diagnostic_from_split(split, scheme, split.hostname)},
        )

    hostname = _normalize_hostname(split.hostname)
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise UrlSecurityError(
            "Localhost destinations are blocked.",
            error_code="blocked_destination",
            details={"url": _diagnostic_from_split(split, scheme, hostname)},
        )

    port = _effective_port(split, scheme, hostname)
    is_ip_literal = _is_ip_literal(hostname)
    request_url = _build_request_url(split, scheme, hostname, port)
    diagnostic_url = sanitize_url_for_diagnostics(request_url)

    return NormalizedUrl(
        original_url=url,
        request_url=request_url,
        diagnostic_url=diagnostic_url,
        scheme=scheme,
        hostname=hostname,
        port=port,
        is_ip_literal=is_ip_literal,
    )


def validate_destination(
    normalized_url: NormalizedUrl,
    *,
    resolver: Resolver = default_resolver,
) -> list[str]:
    if normalized_url.is_ip_literal:
        addresses = [normalized_url.hostname]
    else:
        try:
            addresses = resolver(normalized_url.hostname)
        except UrlNetworkError:
            raise
        except Exception as exc:
            raise UrlNetworkError(
                "DNS resolution failed.",
                error_code="dns_resolution_failed",
                retryable=True,
                details={"url": normalized_url.diagnostic_url},
            ) from exc
        if not addresses:
            raise UrlNetworkError(
                "DNS resolution returned no addresses.",
                error_code="dns_resolution_failed",
                retryable=True,
                details={"url": normalized_url.diagnostic_url},
            )

    for address in addresses:
        validate_public_ip(address, diagnostic_url=normalized_url.diagnostic_url)

    return addresses


def validate_public_ip(address: str, *, diagnostic_url: str | None = None) -> None:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError as exc:
        raise UrlSecurityError(
            "Resolved address is invalid.",
            error_code="blocked_destination",
            details=_url_details(diagnostic_url),
        ) from exc

    blocked = (
        parsed.is_loopback
        or parsed.is_private
        or parsed.is_link_local
        or parsed.is_multicast
        or parsed.is_reserved
        or parsed.is_unspecified
        or (parsed.version == 4 and parsed in SHARED_ADDRESS_SPACE)
        or parsed in METADATA_IPS
        or not parsed.is_global
    )
    if blocked:
        raise UrlSecurityError(
            "Destination address is not public.",
            error_code="blocked_destination",
            details={**_url_details(diagnostic_url), "address": str(parsed)},
        )


def sanitize_url_for_diagnostics(url: str) -> str:
    try:
        split = urlsplit(url)
    except ValueError:
        return "<invalid-url>"

    scheme = split.scheme.lower() if split.scheme else ""
    host = split.hostname or ""
    try:
        host = _normalize_hostname(host)
    except UrlValidationError:
        host = host.lower().rstrip(".")

    try:
        port = split.port
    except ValueError:
        port = None

    netloc = _netloc(host, port)
    return urlunsplit((scheme, netloc, split.path or "", "", ""))


def _normalize_hostname(hostname: str) -> str:
    value = hostname.lower()
    if value.endswith("."):
        value = value[:-1]
    if not value:
        raise UrlValidationError("URL hostname is required.", error_code="invalid_url")

    if _is_ip_literal(value):
        return str(ipaddress.ip_address(value))

    try:
        return value.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise UrlValidationError(
            "URL hostname cannot be normalized.",
            error_code="invalid_url",
        ) from exc


def _effective_port(split: SplitResult, scheme: str, hostname: str) -> int:
    try:
        port = split.port
    except ValueError as exc:
        raise UrlValidationError(
            "URL port is invalid.",
            error_code="disallowed_port",
            details={"url": _diagnostic_from_split(split, scheme, hostname)},
        ) from exc

    expected = 80 if scheme == "http" else 443
    effective = port if port is not None else expected
    if effective != expected:
        raise UrlValidationError(
            "URL port is not allowed.",
            error_code="disallowed_port",
            details={"url": _diagnostic_from_split(split, scheme, hostname)},
        )
    return effective


def _build_request_url(
    split: SplitResult, scheme: str, hostname: str, port: int
) -> str:
    expected_port = 80 if scheme == "http" else 443
    include_port = split.port is not None and port != expected_port
    netloc = _netloc(hostname, port if include_port else None)
    return urlunsplit((scheme, netloc, split.path or "", split.query, ""))


def _diagnostic_from_split(split: SplitResult, scheme: str, hostname: str) -> str:
    return urlunsplit((scheme, _netloc(hostname, None), split.path or "", "", ""))


def _netloc(hostname: str, port: int | None) -> str:
    host = f"[{hostname}]" if ":" in hostname else hostname
    if port is not None:
        return f"{host}:{port}"
    return host


def _is_ip_literal(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return True


def _has_control_or_whitespace(value: str) -> bool:
    return any(
        character.isspace() or ord(character) < 32 or ord(character) == 127
        for character in value
    )


def _url_details(diagnostic_url: str | None) -> dict[str, object]:
    if diagnostic_url is None:
        return {}
    return {"url": diagnostic_url}
