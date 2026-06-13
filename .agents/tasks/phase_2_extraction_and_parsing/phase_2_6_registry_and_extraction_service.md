# Phase 2.6: Extractor Registry and Extraction Service

Parent phase: `phase_2_source_extraction_overview.md`

Depends on:

* `phase_2_1_extraction_core_contracts.md`
* `phase_2_2_docx_extraction.md`
* `phase_2_3_pdf_extraction.md`
* `phase_2_4_url_fetching.md`
* `phase_2_5_html_extraction.md`

## 1. Purpose

Create the minimal application orchestration layer that selects the correct
extractor, builds `ExtractionInput`, coordinates URL fetching for HTML sources,
and converts provider runtime failures into the existing `SourceError` contract.

Phase 2.6 turns the individual providers from Phases 2.2-2.5 into a consistent
application boundary for extraction.

It must not implement API routes, database persistence, file upload handling,
cleaning, chunking, embedding, indexing, retrieval, generation, or crawling.

---

## 2. Scope

Implement:

* `ExtractorRegistry`.
* `ExtractionService`.
* Service-level error wrapper carrying `SourceError`.
* Error mapping from actual fetching and extraction provider exceptions.
* Metadata merge/rejection policy.
* Dependency-injected service wiring.
* Focused unit/integration tests for PDF, DOCX, and URL/HTML flows.

Do not implement:

* FastAPI `UploadFile` handling.
* API routes.
* Request/response API schemas.
* Database repositories.
* Storage.
* Cleaning or chunking.
* Real network calls in tests.
* New parser logic.
* New persistence models.

---

## 3. Service Boundary

`ExtractionService` must be independent of FastAPI.

The future API layer may do:

```text
UploadFile
 -> API route reads bytes
 -> ExtractionService.extract_bytes(...)
```

The service must not expose:

```python
extract(upload_file: UploadFile)
```

This keeps the extraction application layer reusable by API routes, background
jobs, CLI tools, and tests.

---

## 4. Registry Responsibility

`ExtractorRegistry` only selects an extractor provider by `SourceType`.

Required mapping:

```text
SourceType.docx -> DocxExtractor
SourceType.pdf  -> PdfExtractor
SourceType.url  -> HtmlExtractor
```

The registry must not:

* build `ExtractionInput`;
* fetch URLs;
* map errors;
* contain parsing logic;
* manage persistence;
* perform service orchestration.

If a source type is not registered, fail clearly with a service-level error.
Do not fallback to another extractor.

Recommended interface:

```python
class ExtractorRegistry:
    def get(self, source_type: SourceType) -> ContentExtractor:
        ...
```

The registry may validate that registered providers have an `extract` attribute,
but behavior tests are the primary contract proof.

---

## 5. Runtime Protocol Check

Phase 2.6 may update the existing `ContentExtractor` protocol to:

```python
@runtime_checkable
class ContentExtractor(Protocol):
    def extract(self, input_data: ExtractionInput) -> ExtractionResult:
        ...
```

If added, use runtime checks only for fail-fast diagnostics in registry tests.
Do not treat `isinstance(provider, ContentExtractor)` as the main proof that a
provider satisfies the contract.

The main proof remains:

* static type compatibility where available;
* behavior tests using real extractors and fake extractors;
* `ExtractionResult` schema validation.

---

## 6. Service Entry Points

Use two explicit MVP methods instead of one conditional request schema.

Recommended interface:

```python
class ExtractionService:
    def extract_bytes(
        self,
        *,
        source_id: str,
        document_id: str,
        source_type: SourceType,
        content_bytes: bytes,
        source_uri: str | None = None,
        original_filename: str | None = None,
        media_type: str | None = None,
        charset: str | None = None,
        extractor_config: dict[str, object] | None = None,
        extra_metadata: dict[str, object] | None = None,
    ) -> ExtractionResult:
        ...

    def extract_url(
        self,
        *,
        source_id: str,
        document_id: str,
        url: str,
        extractor_config: dict[str, object] | None = None,
        extra_metadata: dict[str, object] | None = None,
    ) -> ExtractionResult:
        ...
```

Rules:

* `extract_bytes()` supports `SourceType.pdf` and `SourceType.docx`.
* `extract_bytes()` must reject `SourceType.url`; URL inputs require
  `extract_url()`.
* `extract_url()` always builds `ExtractionInput(source_type=SourceType.url)`.
* Do not introduce a unified request schema in Phase 2.6 unless a later API
  phase requires it.

---

## 7. URL Orchestration

URL extraction is a special service workflow.

Required flow:

```text
extract_url(url)
 -> UrlFetcher.fetch(url)
 -> FetchedContent
 -> build ExtractionInput(source_type=url)
 -> ExtractorRegistry.get(SourceType.url)
 -> HtmlExtractor.extract(input)
 -> ExtractionResult
```

`ExtractorRegistry` must not call `UrlFetcher`.

`HtmlExtractor` must not call `UrlFetcher`.

`ExtractionInput` for URL should use:

```text
source_uri = fetched.final_url
media_type = fetched.media_type
charset = fetched.charset
content_bytes = fetched.content_bytes
extra_metadata = caller metadata plus service-owned safe fetch metadata
```

Do not put raw HTML bytes into metadata or errors.

---

## 8. Dependency Injection

`ExtractionService` should receive dependencies through its constructor:

```python
ExtractionService(
    registry: ExtractorRegistry,
    url_fetcher: UrlFetcher,
)
```

Do not instantiate concrete providers inside each service call.

Tests should be able to inject:

* fake extractors;
* fake URL fetcher;
* deterministic provider errors;
* real providers for focused integration tests.

A default factory may be added later for application wiring, but the core
service should remain dependency-injected.

---

## 9. Metadata Merge Policy

Caller metadata must not overwrite service-owned metadata.

Reserved top-level metadata keys:

```text
fetch
service
```

If caller-provided `extra_metadata` contains a reserved key, reject the request
with a service input error. Do not silently merge or overwrite.

Example rejected input:

```python
extra_metadata={
    "fetch": {
        "status_code": 999
    }
}
```

For URL extraction, service-owned metadata should be stored under `fetch`:

```python
{
    "fetch": {
        "original_url": fetched.original_url,
        "final_url": fetched.final_url,
        "status_code": fetched.status_code,
        "media_type": fetched.media_type,
        "charset": fetched.charset,
        "redirect_count": fetched.redirect_count,
        "extra_metadata": fetched.extra_metadata,
    }
}
```

Only include safe metadata. Do not include `content_bytes`, raw HTML, query
tokens in diagnostics, cookies, credentials, authorization headers, or document
content.

---

## 10. Error Boundary

Phase 2.6 must create a real application-level error boundary.

Do not merely provide an unused helper while re-raising provider errors.

Recommended wrapper:

```python
class ExtractionServiceError(Exception):
    def __init__(self, source_error: SourceError) -> None:
        self.source_error = source_error
```

Service behavior:

```text
provider error
 -> catch
 -> map to SourceError
 -> raise ExtractionServiceError(source_error) from provider_error
```

This preserves exception chaining while giving future API routes a stable error
shape.

Do not add error details to `SourceError` unless the schema is explicitly
changed in a later phase.

---

## 11. Error Mapping

Mapping must use the actual exception classes currently implemented in:

```text
backend/app/providers/fetching/errors.py
backend/app/providers/extraction/errors.py
```

Do not create aliases or a new taxonomy only for service mapping.

### Fetching Errors

Current fetching taxonomy:

```text
UrlFetchError
UrlValidationError
UrlSecurityError
UrlNetworkError
UrlResponseError
UrlContentTooLargeError
```

For any `UrlFetchError`:

```text
SourceError.error_code = exc.error_code
SourceError.message = exc.message
SourceError.retryable = exc.retryable
SourceError.failed_stage = ProcessingStage.downloading
```

### Extraction Errors

Current extraction taxonomy:

```text
ExtractionError
ExtractionParsingError
ExtractionNoContentError
ExtractionSourceTypeMismatchError
ExtractionInvariantError
```

Mapping:

```text
ExtractionParsingError
 -> failed_stage = ProcessingStage.parsing

ExtractionNoContentError
 -> failed_stage = ProcessingStage.extracting

ExtractionSourceTypeMismatchError
 -> failed_stage = ProcessingStage.extracting

ExtractionInvariantError
 -> failed_stage = ProcessingStage.extracting

fallback ExtractionError
 -> failed_stage = ProcessingStage.extracting
```

For any `ExtractionError`:

```text
SourceError.error_code = exc.error_code
SourceError.message = exc.message
SourceError.retryable = exc.retryable
```

Do not include provider `.details` in `SourceError`, because the existing schema
does not have a details field.

---

## 12. Validation Responsibilities

Service may validate input-level consistency:

* `extract_bytes()` must reject `SourceType.url`.
* `extract_url()` must always use `SourceType.url`.
* reserved metadata keys must be rejected.
* missing registry entry must fail clearly.

Service must not duplicate `ExtractionResult` business validation.

The schema already validates:

* units are non-empty;
* `raw_unit_id` uniqueness;
* `unit_index` uniqueness;
* continuous ordered indexes from `0`;
* unit lineage matches result lineage;
* `stats.total_units` matches `len(units)`;
* `stats.warning_count` matches `len(warnings)`.

Let `ExtractionResult` and extractors own those invariants.

---

## 13. Expected Files

Expected additions or modifications:

```text
backend/app/providers/extraction/interface.py
backend/app/services/extraction.py
backend/tests/test_extraction_service.py
```

Optional if it matches local style:

```text
backend/app/services/__init__.py
```

Do not add API routes, repositories, migrations, or database models.

---

## 14. Tests

Add focused tests for:

* registry returns the DOCX extractor for `SourceType.docx`;
* registry returns the PDF extractor for `SourceType.pdf`;
* registry returns the HTML extractor for `SourceType.url`;
* registry fails clearly for unregistered source type;
* optional runtime protocol check does not replace behavior tests;
* `extract_bytes()` builds `ExtractionInput` and calls the registered extractor;
* `extract_bytes()` rejects `SourceType.url`;
* `extract_url()` calls `UrlFetcher` before `HtmlExtractor`;
* `extract_url()` uses `FetchedContent.final_url` as `source_uri`;
* URL `media_type`, `charset`, and bytes are copied into `ExtractionInput`;
* caller metadata cannot use reserved keys;
* caller metadata is preserved when non-reserved;
* service-owned `fetch` metadata cannot be overwritten;
* fetching provider errors map to `ExtractionServiceError.source_error`;
* extraction provider errors map to `ExtractionServiceError.source_error`;
* retryability and stable `error_code` are preserved;
* exception chaining preserves the original provider error as `__cause__`;
* service does not call real network in tests;
* successful PDF, DOCX, and URL/HTML flows return `ExtractionResult`.

Run:

```text
pytest
```

---

## 15. Acceptance Criteria

Phase 2.6 is complete when:

* `ExtractorRegistry` only selects extractors.
* `ExtractionService` has explicit `extract_bytes()` and `extract_url()`
  entry points.
* Service does not accept FastAPI `UploadFile`.
* URL extraction orchestrates fetcher then HTML extractor.
* Provider dependencies are injected.
* Caller metadata cannot overwrite service-owned metadata.
* Provider errors are mapped to `SourceError` through a real service error
  boundary.
* Mapping uses actual existing provider exception classes.
* Service does not reimplement `ExtractionResult` schema validation.
* No API, repository, persistence, cleaning, chunking, embedding, indexing, or
  generation behavior is added.
* Full backend regression passes.
