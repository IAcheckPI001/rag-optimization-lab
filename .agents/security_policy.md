## Security Policy Instructions

Use this file before changing URL ingestion, file upload, crawling, external
fetching, provider calls, content extraction, or logging of user-provided
content.

## Core Security Rules

- Do not store secrets in code.
- Do not log secrets, API keys, authorization headers, cookies, or private
  credentials.
- Do not execute uploaded files.
- Do not store uploads in a public web root.
- Do not bypass captcha, login, paywall, authentication, robots restrictions, or
  anti-bot systems.
- Do not crawl private, authenticated, paywalled, social media, captcha, or
  anti-bot pages by default.

## URL Ingestion

MVP supports a single public website URL only.

Before fetching:
- Accept only `http` and `https` URLs.
- Reject missing hosts and malformed URLs.
- Reject localhost names such as `localhost`.
- Reject private, loopback, link-local, multicast, and reserved IP ranges.
- Reject cloud metadata IPs, including `169.254.169.254`.
- Resolve hostnames safely before fetching.

After redirects:
- Re-validate the final URL.
- Re-check the final host/IP.
- Enforce redirect limits.
- Reject redirects to blocked hosts or IP ranges.

Fetching rules:
- Use reasonable timeout limits.
- Use response size limits when implemented.
- Do not send user secrets or internal credentials.
- Do not use authenticated browser automation.
- Do not use Playwright in MVP.

If SSRF validation behavior is not implemented yet and a task touches URL
fetching, implement or propose the validation first.

## Blocked URL Targets

Block at minimum:
- `localhost` and loopback addresses.
- Private IPv4 ranges.
- Private IPv6 ranges.
- Link-local ranges.
- Cloud metadata addresses.
- Internal hostnames when they resolve to blocked ranges.

If exact IP range handling is being implemented, add tests for normal public
hosts, localhost, private IPs, metadata IPs, and redirect-to-private cases.

## File Uploads

MVP allows only:
- PDF.
- DOCX.

Upload rules:
- Validate file extension and content type where practical.
- Reject unsupported file types.
- Apply file size limits when implemented.
- Do not execute uploaded files.
- Do not store uploads in a public web root.
- Treat extracted content as untrusted input.

PDF and DOCX extraction should be done through controlled libraries and provider
interfaces. Do not shell out to execute uploaded content.

## External Providers

External providers include OpenAI, Qdrant, public website fetching, document
extractors, and any future reranking provider.

Rules:
- API routes must not call providers directly.
- Provider calls must go through provider interfaces.
- Secrets must come from environment-backed settings.
- Unit tests must mock provider behavior.
- Unit tests must not call real providers or real websites.

## Logging And Privacy

Safe logging examples:
- Document id.
- Chunk count.
- Source type.
- Retrieval method.
- Provider name.
- Error category.

Avoid logging:
- API keys.
- Authorization headers.
- Cookies.
- Full raw uploaded documents.
- Full web page contents.
- Private URLs or credentials embedded in URLs.

If detailed content logging is required for debugging, ask for approval and make
the behavior explicit, bounded, and disabled by default.

## Security Tests

When changing URL ingestion, file upload, or external fetching, include tests
for:
- Normal allowed case.
- Blocked localhost/private/metadata case.
- Redirect or malformed-input failure case when relevant.

Tests must not fetch real websites. Use mocked fetchers or local fake provider
objects.
