# Phase 2.4: URL Fetching

Parent phase: `phase_2_source_extraction_overview.md`

Depends on:

* `phase_2_1_extraction_core_contracts.md`
* `phase_2_2_docx_extraction.md`
* `phase_2_3_pdf_extraction.md`

## 1. Purpose

Implement a URL fetching provider that downloads exactly one user-supplied
public HTML document and returns the existing `FetchedContent` schema.

Target flow:

```text
Public URL
 -> URL normalization and validation
 -> DNS and public-destination validation
 -> bounded HTTP GET
 -> FetchedContent
```

Phase 2.4 performs network fetching only.

It must not parse HTML or create `RawDocumentUnit` objects.

---

## 2. Scope

Implement:

* HTTP/HTTPS URL validation.
* URL normalization for validation and redirect-loop detection.
* Public-destination validation.
* DNS resolution and SSRF checks.
* Manual redirect handling.
* Request timeout limits.
* Total fetch deadline.
* Redirect count limits.
* Decoded response size limits.
* HTTP status validation.
* HTML/XHTML content-type validation.
* Safe response metadata.
* Sanitized diagnostic URLs for errors.
* Fetching-specific runtime errors.
* Mocked focused tests.

Do not implement:

* HTML parsing.
* BeautifulSoup or trafilatura.
* JavaScript rendering.
* Browser automation.
* Link crawling.
* Multi-page crawling.
* `robots.txt` fetching.
* Authentication.
* Cookies.
* POST requests.
* File downloading.
* API routes.
* Extraction service orchestration.
* Persistence.
* Cleaning or chunking.

---

## 3. Dependency

Add `httpx` as a runtime dependency according to the current
`backend/pyproject.toml` dependency style.

If `httpx` already exists in optional test dependencies, move it to runtime
dependencies without creating an unnecessary duplicate declaration.

Do not add:

```text
requests
aiohttp
Playwright
Selenium
BeautifulSoup
trafilatura
robots.txt parsers
malware scanners
```

---

## 4. Expected Files

Expected additions or modifications:

```text
backend/pyproject.toml
backend/app/providers/fetching/interface.py
backend/app/providers/fetching/errors.py
backend/app/providers/fetching/url_security.py
backend/app/providers/fetching/httpx_url_fetcher.py
backend/tests/test_url_fetcher.py
```

File names may follow actual repository conventions, but fetching must remain
separate from extraction.

Do not make `HtmlExtractor` perform HTTP requests.

---

## 5. Existing Output Contract

Reuse the Phase 2.1 `FetchedContent` schema.

The fetcher output must contain:

* `original_url`
* `final_url`
* `content_bytes`
* `media_type`
* `charset`
* `status_code`
* `redirect_count`
* safe `extra_metadata`

Do not add:

```text
source_id
document_id
source_type
RawDocumentUnit
ExtractionResult
```

Lineage will be added by the extraction service in a later phase.

---

## 6. Fetcher Contract

Recommended contract:

```python
class UrlFetcher(Protocol):
    def fetch(self, url: str) -> FetchedContent:
        ...
```

Recommended implementation:

```python
class HttpxUrlFetcher:
    def fetch(self, url: str) -> FetchedContent:
        ...
```

Use a synchronous contract unless the existing architecture explicitly requires
an asynchronous provider.

Do not make the protocol runtime-checkable in this phase unless the shared
interface policy is intentionally updated.

The provider must perform no automatic retries. Retry and backoff policy belongs
to a future service or background-job layer where total attempts can be
accounted for safely.

---

## 7. Fetch Policy

Keep all fetch limits in one immutable policy object or equivalent internal
configuration.

Recommended MVP defaults:

```text
allowed schemes: http, https
effective HTTP port: 80
effective HTTPS port: 443
maximum redirects: 5
maximum decoded response size: 5 MiB
connect timeout: 5 seconds
read timeout per chunk: 10 seconds
write timeout: 5 seconds
pool timeout: 5 seconds
total fetch deadline: 30 seconds
```

The total fetch deadline applies to the whole fetch operation, including all
redirect hops and streaming the final body. It must not reset after each
redirect.

Use monotonic time for deadline checks. If the total deadline is exceeded, close
the active response and raise a network/deadline fetching error.

Each request hop must cap HTTPX operation timeouts by the remaining total
deadline budget:

```text
remaining = deadline_at - monotonic()
```

If `remaining <= 0`, raise `UrlNetworkError` with
`error_code="request_deadline_exceeded"` before starting the hop.

This does not provide hard real-time cancellation for every blocking operation,
but it prevents a new request hop from starting with full per-operation timeouts
when the overall fetch budget is nearly exhausted.

Do not hard-code the same limit in multiple modules.

Custom public ports are out of scope unless explicitly approved.

---

## 8. URL Normalization And Validation

Reject:

* Blank URLs.
* Relative URLs.
* Missing hostnames.
* Unsupported schemes.
* URL credentials or userinfo.
* Invalid ports.
* Disallowed ports.
* Control characters.
* Malformed whitespace.
* `localhost` and `*.localhost`.
* Hostnames that cannot be normalized through IDNA.

Allow only:

```text
http
https
```

Normalization rules:

* Lowercase scheme for validation.
* Lowercase hostname for validation.
* Remove one trailing dot from the hostname before security checks.
* Convert internationalized hostnames consistently through IDNA before DNS
  lookup.
* Strip fragments before requesting.
* Preserve path and query for the actual request.
* Do not aggressively normalize path segments.
* Do not decode all percent-encoding.
* Do not collapse path segments in a way that may change the resource seen by
  the server.

IP literals must be detected directly before DNS resolution. Do not send IP
literals through the DNS resolver.

Use the normalized, fragment-free URL for redirect-loop detection.

Keep query parameters for the request, but do not expose full query strings in
logs, errors, or safe metadata because they may contain secrets.

---

## 9. Effective Port Semantics

Use conservative MVP port policy:

```text
http  -> effective port 80
https -> effective port 443
```

Rules:

* A URL without an explicit port uses the scheme default.
* `http://example.com` is allowed with effective port `80`.
* `https://example.com` is allowed with effective port `443`.
* `http://example.com:80` is allowed.
* `https://example.com:443` is allowed.
* HTTP ports other than `80` are rejected.
* HTTPS ports other than `443` are rejected.
* Custom public ports are rejected in Phase 2.4.

This prevents the fetcher from becoming a generic scanner for arbitrary public
or internal services on custom ports.

---

## 10. SSRF And DNS Validation

Resolve the hostname before every request unless the target is an IP literal.

Validate all IPv4 and IPv6 addresses returned by the resolver.

If the hostname resolves to multiple addresses, every address must pass the
public-destination policy. Reject the entire target if any resolved address is
blocked or non-public.

Reject empty DNS results.

Reject DNS resolution failures with a network/dns fetching error.

Reject addresses that are:

* Loopback.
* Private.
* Link-local.
* Multicast.
* Reserved.
* Unspecified.
* Shared address space `100.64.0.0/10`.
* Known cloud metadata targets.
* Not globally routable.

Explicitly block common metadata targets such as:

```text
169.254.169.254
```

Do not rely only on `address.is_private`. In Python, shared address space
`100.64.0.0/10` may have both `is_private == False` and `is_global == False`,
so it must be blocked explicitly.

The same validation must be performed for every redirect destination.

DNS rebinding limitation:

* Phase 2.4 pre-resolves and validates every hop.
* HTTPX may still resolve the hostname again when opening the connection.
* This leaves a time-of-check/time-of-use residual risk.
* This residual risk is accepted for MVP and must be documented.

Synchronous DNS limitation:

* The default resolver may use blocking system DNS resolution.
* A total fetch deadline can be checked before and after DNS resolution, but it
  cannot forcibly interrupt a blocking `getaddrinfo()` call.
* Resolver timeout control is a residual MVP limitation unless a timeout-aware
  resolver is injected by a later infrastructure boundary.

Do not implement IP pinning, custom transports, outbound proxy integration, or
network namespace isolation in Phase 2.4 unless separately approved.

Production hardening may later require one or more of:

```text
outbound proxy
egress firewall
network namespace or container isolation
destination allowlist
connection pinning to validated IPs
cloud metadata blocking at the network layer
```

---

## 11. HTTP Client Configuration

Use HTTPX with:

```text
follow_redirects=False
verify=True
trust_env=False
```

Use bounded timeout values from the fetch policy.

Send only safe headers:

```text
User-Agent
Accept: text/html, application/xhtml+xml
Accept-Encoding: identity
```

`Accept-Encoding: identity` reduces compression-bomb risk, but it is not the
only protection. The implementation must still stream and count decoded bytes.

Do not send:

* Cookies.
* Authentication.
* Authorization headers.
* Proxy authorization.
* Browser session data.

Use GET only.

Do not disable TLS verification.

Do not use automatic retries.

When the fetcher creates the HTTPX transport itself, configure transport-level
retries as zero. Injected transports are treated as caller-owned test or
integration dependencies, but Phase 2.4 provider behavior must not add its own
retry loop.

---

## 12. Client And Response Lifecycle

Client ownership must be explicit.

Rules:

* If `HttpxUrlFetcher` creates its own client, it owns and closes that client.
* If a client is injected from outside, the fetcher must not close it.
* Every streamed response must be opened with a context manager or equivalent
  `try/finally`.
* The response must be closed on success and every error path.
* `FetchedContent` must not contain HTTPX client, response, request, transport,
  or resolver objects.

Tests should verify response lifecycle through mocked boundaries where
practical, without over-coupling to HTTPX internals.

---

## 13. Redirect Handling

Handle redirects manually.

Supported redirect statuses:

```text
301
302
303
307
308
```

For every redirect:

1. Require a valid `Location`.
2. Resolve relative locations against the current URL using URL joining.
3. Strip fragments.
4. Normalize scheme and hostname.
5. Validate credentials and effective port.
6. Resolve and validate IP or DNS again.
7. Compare against a visited set of normalized, fragment-free URLs.
8. Reject redirect loops.
9. Enforce the redirect limit.
10. Request the next validated destination.

Allow HTTP-to-HTTPS redirects.

Reject HTTPS-to-HTTP downgrade redirects in the MVP.

Cross-host redirects are allowed only when the new target passes the complete
validation policy.

Because only GET is supported, all supported redirect statuses continue with
GET. Do not carry POST semantics into Phase 2.4.

---

## 14. HTTP Status Validation

Redirect statuses are handled separately.

The final response must have a successful 2xx status.

Reject:

* Unexpected final 3xx.
* `204 No Content`.
* `205 Reset Content`.
* `206 Partial Content`.
* `304 Not Modified`.
* 4xx.
* 5xx.

`204` and `205` must fail as empty responses.

`206` is rejected because partial content is not supported.

`304` is rejected because conditional requests and cache validation are not
implemented.

A successful response with an empty streamed body must still fail with an
empty-response fetching error.

---

## 15. Header Validation

Validate headers deterministically.

`Content-Length` rules:

* Missing `Content-Length` is allowed; rely on streamed byte counting.
* A valid non-negative integer larger than the configured limit is rejected
  early.
* A valid non-negative integer at or below the limit still requires streaming
  byte counting.
* Invalid, malformed, or non-integer `Content-Length` is rejected.
* Negative `Content-Length` is rejected.
* Multiple conflicting `Content-Length` values are rejected when observable
  through the client boundary.

`Content-Type` rules:

* Missing `Content-Type` is rejected.
* Malformed `Content-Type` is rejected.
* Duplicate or conflicting `Content-Type` values are rejected when observable
  through the client boundary.
* Parse media type and charset structurally rather than using raw string
  comparison.

When HTTPX combines duplicate headers into one value, use one deterministic
parsing policy and fail closed on ambiguity.

---

## 16. Content-Type Validation

Normalize the response media type.

Accept only:

```text
text/html
application/xhtml+xml
```

Reject:

* Missing Content-Type.
* Malformed Content-Type.
* text/plain.
* application/json.
* application/pdf.
* image types.
* application/octet-stream.
* Any other unsupported media type.

Do not MIME-sniff arbitrary binary content into HTML.

Do not treat a valid Content-Type as proof that the body is trusted or safe.

Phase 2.4 does not execute or render the response.

---

## 17. Bounded Streaming

Download the response through HTTPX streaming.

Do not access the full `response.content` before applying the response-size
limit.

Use two checks:

1. Reject early when a valid `Content-Length` exceeds the configured limit.
2. Count streamed decoded bytes and stop when the actual body exceeds the
   configured limit.

Use `response.iter_bytes()` for decoded bytes because those are the bytes passed
to the future HTML parser.

Do not trust `Content-Length` as the only protection.

The exactly-at-limit response must be accepted.

An over-limit response must be stopped and closed without returning partial
content.

The total fetch deadline must also be checked while streaming. A slow-drip
server that sends tiny chunks before each read timeout must still be stopped
when the total deadline is exceeded.

---

## 18. Empty Content

If the streamed response body is empty, raise the appropriate fetching error.

Do not construct an empty `FetchedContent`.

---

## 19. FetchedContent Construction

Build:

```python
FetchedContent(
    original_url=...,
    final_url=...,
    content_bytes=...,
    media_type=...,
    charset=...,
    status_code=...,
    redirect_count=...,
    extra_metadata={
        "downloaded_bytes": ...,
        "content_length_header": ...,
    },
)
```

Only include metadata that is safe, bounded, and useful.

Do not store:

* Full response headers.
* Set-Cookie.
* Authorization values.
* Full query tokens.
* Duplicate response content.
* HTTPX objects.
* Resolver objects.

`content_bytes` must remain excluded from model dumps and repr according to the
existing schema.

`original_url` and `final_url` may preserve the full request URL according to
the schema contract. They must not be copied into provider error details or logs
without sanitization.

---

## 20. Safe Diagnostic URLs

Create a pure helper for safe diagnostic URLs.

Diagnostic URL format:

```text
scheme://host[:safe-port]/path
```

Diagnostic URLs must not contain:

```text
query
fragment
userinfo
password
token values
```

Example:

```text
input:      https://example.com/page?token=secret&user=123#section
diagnostic: https://example.com/page
```

Use sanitized diagnostic URLs in provider error details and safe metadata.

---

## 21. Fetching Error Taxonomy

Create provider-level fetching errors.

Recommended categories:

```text
UrlFetchError
UrlValidationError
UrlSecurityError
UrlNetworkError
UrlResponseError
UrlContentTooLargeError
```

Use stable error codes such as:

```text
invalid_url
unsupported_scheme
userinfo_not_allowed
disallowed_port
blocked_destination
dns_resolution_failed
request_timeout
request_deadline_exceeded
network_error
redirect_limit_exceeded
redirect_loop
invalid_redirect
https_downgrade_redirect
http_status_error
unsupported_content_type
malformed_content_type
invalid_content_length
response_too_large
empty_response
```

Do not use `SourceError` inside the provider.

Mapping to:

```text
ProcessingStage.downloading
```

belongs to the extraction service phase.

Errors must not contain:

* Response body.
* Raw content bytes.
* Cookies.
* Authorization data.
* Full headers.
* Sensitive query parameters.

---

## 22. Expected Behavior Matrix

| Case | Expected result |
| --- | --- |
| Blank URL | `UrlValidationError` |
| Relative URL | `UrlValidationError` |
| `file:`, `ftp:`, `javascript:` | `UrlValidationError` |
| URL with credentials/userinfo | `UrlValidationError` |
| HTTP port other than `80` | `UrlValidationError` |
| HTTPS port other than `443` | `UrlValidationError` |
| Private/internal IP literal | `UrlSecurityError` before request |
| Hostname DNS returns public + private IPs | `UrlSecurityError` for whole target |
| Redirect to private/internal destination | `UrlSecurityError` |
| Redirect loop | redirect error |
| HTTPS to HTTP redirect | security or downgrade redirect error |
| Missing or unsupported Content-Type | response/content-type error |
| Empty body | empty-response error |
| Body exceeds limit | stop stream, close response, no partial result |
| Timeout or total deadline exceeded | `UrlNetworkError` |
| Valid HTML or XHTML | return `FetchedContent` |

---

## 23. Untrusted Content Boundary

A successful fetch means only that the response is eligible for controlled
parsing.

It does not mean the website or content is trusted.

Fetched bytes must be treated as untrusted data.

Phase 2.4 must not:

* Execute JavaScript.
* Render HTML.
* Load scripts, stylesheets, images, fonts, iframes, or other subresources.
* Follow links found inside HTML.
* Save content to an executable or publicly served location.
* Serve raw fetched HTML back to a browser.
* Interpret document text as system instructions.

Malware detection, HTML sanitization, parser hardening, prompt-injection
defense, and safe UI rendering belong to later boundaries.

---

## 24. Robots Policy

Phase 2.4 fetches exactly one user-supplied public URL.

It does not crawl or discover links.

`robots.txt` evaluation is deferred to a future ingestion-policy or crawling
phase.

Do not add `robots.txt` fetching in Phase 2.4, because that creates another
network request with its own redirect, DNS, timeout, error, and SSRF handling
complexity.

When multi-page crawling is implemented later, robots policy must be revisited
before crawling child links.

---

## 25. Testability

Allow dependency injection for:

* HTTPX transport or client factory.
* DNS resolver.
* Fetch policy.
* Monotonic clock or deadline checker when needed for deterministic deadline
  tests.

Tests must use mocked transports and fake DNS resolution.

No test may call the public internet.

---

## 26. Required Tests

### URL validation and normalization

Test:

* Valid HTTP URL.
* Valid HTTPS URL.
* Blank URL.
* Relative URL.
* Missing hostname.
* Unsupported schemes.
* Credentials in URL.
* Invalid and disallowed ports.
* Control characters.
* Malformed whitespace.
* Localhost names.
* Hostname trailing dot normalization.
* Uppercase scheme and hostname normalization.
* IDNA hostname handling.
* IP literals validated directly without DNS resolver.
* URL fragment stripped.
* Query preserved for request but not diagnostics.

### SSRF

Test:

* IPv4 loopback.
* IPv6 loopback.
* Private IPv4 ranges.
* Private IPv6 ranges.
* Link-local addresses.
* Cloud metadata address.
* Shared address space `100.64.0.0/10`.
* Multicast and reserved IPs.
* Unspecified IPs.
* Hostname resolving to a private IP.
* Mixed public/private DNS results.
* DNS failure.
* Empty resolution result.

### Redirects

Test:

* Relative public redirect.
* Cross-host public redirect.
* HTTP-to-HTTPS.
* HTTPS-to-HTTP rejection.
* Redirect to private destination.
* Redirect loop using normalized URLs.
* Redirect loop with fragment/case/trailing-dot variants when practical.
* Missing Location.
* Redirect limit exceeded.
* Redirect preserves GET-only behavior.

### HTTP behavior

Test:

* Successful HTML.
* Successful XHTML.
* Unexpected final 3xx.
* `204` and `205`.
* `206`.
* `304`.
* 4xx.
* 5xx.
* Connect timeout.
* Read timeout.
* Total fetch deadline exceeded.
* Per-hop timeout capped by remaining total deadline budget.
* Network failure.
* TLS-related failure when practical through the mocked boundary.
* No automatic retries.

### Headers and content

Test:

* Charset parsing.
* Missing Content-Type.
* Malformed Content-Type.
* Unsupported Content-Type.
* Duplicate or conflicting Content-Type when observable.
* Empty response.
* Content-Length over limit.
* Invalid Content-Length.
* Negative Content-Length.
* Conflicting Content-Length when observable.
* Streamed decoded body over limit.
* Body exactly at limit.
* Unicode HTML bytes.
* `Accept-Encoding: identity` is sent.

### Contract and safety

Test:

* `original_url`.
* `final_url`.
* `status_code`.
* `redirect_count`.
* `media_type`.
* `charset`.
* `downloaded_bytes`.
* `content_bytes` excluded from repr and model dumps.
* Safe diagnostic URL excludes query, fragment, and userinfo.
* No sensitive headers or query tokens in errors or metadata.
* Response and client lifecycle are closed on success and failures.
* Owned client or transport is closed after fetch.
* Injected client is not closed by the fetcher.
* Response stream is closed after over-limit or error paths.
* No real network calls.

---

## 27. Explicitly Out Of Scope

Do not implement:

```text
HTML parsing
main-content detection
DOM traversal
BeautifulSoup
trafilatura
JavaScript rendering
browser automation
robots.txt fetching
sitemap processing
link crawling
multi-page ingestion
authentication
cookies
form submission
file downloads
PDF or DOCX fetching behavior
ExtractorRegistry
ExtractionService
API routes
database persistence
cleaning
chunking
embedding
indexing
retrieval
malware scanning
HTML sanitization
prompt-injection classification
IP pinning
custom HTTP transport
outbound proxy integration
network namespace isolation
```

Do not modify unrelated modules or shared schemas unless an actual blocker is
reported.

---

## 28. Acceptance Criteria

Phase 2.4 is complete only when:

1. HTTPX is available as a runtime dependency.
2. URL fetching is separate from HTML extraction.
3. Only HTTP and HTTPS public destinations are accepted.
4. URL userinfo, disallowed ports, localhost, and internal IPs are rejected.
5. URL normalization rules are implemented and tested.
6. Effective port mapping is enforced by scheme.
7. Explicit IP deny checks and global-routability requirements are enforced.
8. Mixed DNS results are rejected.
9. Every redirect target is revalidated.
10. Redirect count and normalized loop protection work.
11. TLS verification remains enabled.
12. Environment proxy configuration is not trusted implicitly.
13. No automatic retries happen inside the provider.
14. Provider-owned HTTP transport uses zero retries.
15. Request operation timeouts and a total fetch deadline are bounded.
16. Each hop timeout is capped by the remaining total deadline budget.
17. `Accept-Encoding: identity` is sent.
18. Response body size is bounded during decoded-byte streaming.
19. Only HTML and XHTML responses are accepted.
20. Header edge cases are handled deterministically.
21. Successful output is a valid `FetchedContent`.
22. Raw bytes are excluded from repr and serialized dumps.
23. No HTML parsing or `RawDocumentUnit` creation is added.
24. Errors and metadata do not expose secrets, query tokens, headers, or body
    content.
25. Sanitized diagnostic URLs are used for errors.
26. Tests use mocked HTTP and DNS behavior.
27. Focused tests pass.
28. Related Phase 2 tests pass.
29. Full backend regression passes.
30. DNS-rebinding, synchronous-DNS, untrusted-content, and deferred-robots limitations are
    documented.

---

## 29. Implementation Rule

Implement only Phase 2.4.

Before implementation:

1. Read `backend/AGENTS.md`.
2. Read `.agents/architecture.md`.
3. Read `.agents/security_policy.md`.
4. Read the Phase 2 overview.
5. Inspect the actual Phase 2.1 `FetchedContent` schema.
6. Inspect current provider and error conventions.
7. Inspect the completed DOCX and PDF providers.
8. Inspect the current runtime dependency layout.
9. Confirm the expected synchronous interface.
10. Report any conflict that requires a shared contract or architecture change.

Only stop for clarification when a conflict requires changing:

* A shared schema.
* A public provider interface.
* An approved dependency.
* API or database contracts.
* The agreed Phase 2.4 scope.

After implementation, report:

* Dependency changes.
* Files created and modified.
* URL normalization behavior.
* Effective port behavior.
* SSRF, IP, and DNS behavior.
* Redirect behavior.
* Timeout, total deadline, and size-limit behavior.
* Header and content-type behavior.
* `FetchedContent` output behavior.
* Error taxonomy.
* Safe diagnostic URL behavior.
* Client and response lifecycle behavior.
* Security limitations.
* Focused test result.
* Related test result.
* Full regression result.
* Any contract conflict or deferred issue.
