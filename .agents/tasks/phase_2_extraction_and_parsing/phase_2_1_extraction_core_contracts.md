# Phase 2.1: Extraction Core Contracts

## 1. Purpose

Phase 2.1 defines the shared extraction contracts used by later DOCX, PDF, HTML,
URL fetching, and extraction service phases.

This sub-phase must not implement real DOCX, PDF, HTML, or HTTP parsing. It only
creates the schemas, provider protocol, deterministic ID helper, runtime error
types, and validation tests that future extractors must follow.

The core direction is:

```text
source bytes or fetched HTML bytes
 -> ExtractionInput
 -> ContentExtractor
 -> ExtractionResult
```

Phase 2.1 does not implement:

- DOCX parsing.
- PDF parsing.
- HTML parsing.
- URL fetching.
- Cleaning.
- Chunking.
- Embedding.
- Indexing.
- Retrieval.
- Database persistence.
- API routes.
- Parser or HTTP dependencies.

## 2. Files To Update Or Add

Update:

```text
backend/app/schemas/document.py
backend/app/providers/extraction/interface.py
backend/tests/test_document_schema.py
```

Add:

```text
backend/app/schemas/extraction.py
backend/app/providers/extraction/errors.py
backend/app/providers/extraction/ids.py
backend/tests/test_extraction_schema.py
backend/tests/test_extraction_interface.py
backend/tests/test_extraction_errors.py
backend/tests/test_extraction_ids.py
```

Do not add dependencies in `pyproject.toml` during Phase 2.1.

## 3. RawDocumentUnit Update

Add `unit_index` to `RawDocumentUnit` only.

```python
class RawDocumentUnit(DocumentUnitBase):
    raw_unit_id: NonEmptyStr
    unit_index: int = Field(ge=0)
    extracted_at: datetime
```

Rules:

- `unit_index` is required.
- `unit_index` starts at `0`.
- `unit_index` must represent extraction output order.
- `unit_index` is not added to `DocumentUnitBase`.
- `unit_index` is not added to `CleanDocumentUnit`.
- `unit_index` is not added to `DocumentChunk`.
- Extractors must not pass `character_count`, `word_count`, or `content_hash`.
- `character_count`, `word_count`, and `content_hash` remain derived computed
  fields on `DocumentUnitBase`.

## 4. Extraction Schemas

Create the Phase 2 extraction schemas in:

```text
backend/app/schemas/extraction.py
```

All schemas must inherit from `PipelineSchema`, so unknown fields are rejected by
default.

### 4.1 ExtractionInput

`ExtractionInput` is the shared input contract for all content extractors.

```python
class ExtractionInput(PipelineSchema):
    source_id: NonEmptyStr
    document_id: NonEmptyStr
    source_type: SourceType
    source_uri: NonEmptyStr | None = None
    original_filename: NonEmptyStr | None = None
    media_type: NonEmptyStr | None = None
    charset: NonEmptyStr | None = None
    content_bytes: bytes = Field(min_length=1, exclude=True, repr=False)
    extractor_config: dict[str, object] = Field(default_factory=dict)
    extra_metadata: dict[str, object] = Field(default_factory=dict)
```

Field meaning:

- `source_id`: source lineage identifier.
- `document_id`: logical document identifier.
- `source_type`: one of `pdf`, `docx`, or `url`.
- `source_uri`: optional non-empty source URI or final URL.
- `original_filename`: optional original file name for file upload provenance.
- `media_type`: optional input MIME type.
- `charset`: optional text charset, mainly useful for HTML extraction.
- `content_bytes`: raw binary content to extract from.
- `extractor_config`: safe extractor configuration metadata.
- `extra_metadata`: flexible safe debug/provenance metadata.

Rules:

- `content_bytes` must be non-empty.
- `content_bytes` must be excluded from `model_dump()`.
- `content_bytes` must be hidden from `repr()`.
- The schema must not expose FastAPI upload objects.
- The schema must not expose parser objects.
- The schema must not expose database records.
- The schema must not expose local filesystem paths as shared contract fields.
- `source_uri` only rejects empty or whitespace-only values; URL and SSRF
  validation belong to Phase 2.4.
- Use `extractor_config`, not `parser_config`, because the shared abstraction is
  `ContentExtractor` and HTML extraction is not always purely parser behavior.

### 4.2 FetchedContent

`FetchedContent` is the low-level HTTP content contract returned by the future
URL fetcher. It must not carry source/document lineage.

```python
class FetchedContent(PipelineSchema):
    original_url: NonEmptyStr
    final_url: NonEmptyStr
    content_bytes: bytes = Field(min_length=1, exclude=True, repr=False)
    media_type: NonEmptyStr | None = None
    charset: NonEmptyStr | None = None
    status_code: int = Field(ge=100, le=599)
    redirect_count: int = Field(default=0, ge=0)
    extra_metadata: dict[str, object] = Field(default_factory=dict)
```

Rules:

- Do not include `source_id`.
- Do not include `source_type`.
- The future `ExtractionService` converts `FetchedContent` into
  `ExtractionInput`.
- Use `media_type`, not `content_type`.
- Use `status_code`, not `http_status`.
- `status_code` is required because `FetchedContent` represents a successful
  HTTP fetch result. If no valid HTTP response exists, do not create
  `FetchedContent`.
- `content_bytes` must be non-empty.
- `content_bytes` must be excluded from `model_dump()`.
- `content_bytes` must be hidden from `repr()`.

Boundary:

```text
UrlFetcher
 -> FetchedContent

ExtractionService
 -> ExtractionInput with source/document lineage

HtmlExtractor
 -> ExtractionResult containing RawDocumentUnit objects
```

### 4.3 ExtractionStats

`ExtractionStats` describes a successful extraction result. A successful result
must contain at least one extracted unit.

```python
class ExtractionStats(PipelineSchema):
    total_units: int = Field(ge=1)
    skipped_items: int = Field(default=0, ge=0)
    warning_count: int = Field(ge=0)
    extra_metadata: dict[str, object] = Field(default_factory=dict)
```

Rules:

- `total_units` must be at least `1`.
- If no units can be extracted, future extractors must raise
  `ExtractionNoContentError`.
- Future extractors must not return a successful `ExtractionResult` with
  `units=[]`.
- Use `skipped_items`, not `skipped_units`, because skipped blocks/items never
  became units.
- Parser-specific counters such as page counts, paragraph counts, table counts,
  HTML tag counts, or block counts belong in `extra_metadata` unless later
  promoted to stable cross-extractor fields.

### 4.4 ExtractionWarning

`ExtractionWarning` describes non-fatal parser or extraction issues.

```python
class ExtractionWarning(PipelineSchema):
    warning_code: NonEmptyStr
    message: NonEmptyStr
    stage: ProcessingStage
    item_index: int | None = Field(default=None, ge=0)
    unit_index: int | None = Field(default=None, ge=0)
    extra_metadata: dict[str, object] = Field(default_factory=dict)
```

Allowed warning stages in Phase 2.1:

- `ProcessingStage.parsing`
- `ProcessingStage.extracting`

Rules:

- Do not hard-code every warning to `extracting`.
- Use `parsing` for warnings that occur while opening or interpreting source
  structure.
- Use `extracting` for warnings related to skipped unsupported objects, skipped
  blank blocks, malformed tables, or unit construction.
- `item_index` refers to a parser-native item or block position.
- `unit_index` refers only to a unit that was actually created.
- Negative positions must be rejected.
- Fatal failures must become runtime extraction errors, not warnings.

### 4.5 ExtractionResult

`ExtractionResult` is the successful output contract for every content
extractor.

```python
class ExtractionResult(PipelineSchema):
    source_id: NonEmptyStr
    document_id: NonEmptyStr
    source_type: SourceType
    extractor_name: NonEmptyStr
    extractor_version: NonEmptyStr
    units: list[RawDocumentUnit]
    warnings: list[ExtractionWarning] = Field(default_factory=list)
    stats: ExtractionStats
```

Aggregate validation rules:

- `units` must not be empty.
- `raw_unit_id` values must be unique.
- `unit_index` values must be unique.
- `unit_index` values must be continuous from `0`.
- The list order of `units` must match `unit_index`.
- Every unit must have the same `source_id` as the result.
- Every unit must have the same `document_id` as the result.
- Every unit must have the same `source_type` as the result.
- `stats.total_units == len(units)`.
- `stats.warning_count == len(warnings)`.

Invalid no-content output:

```python
ExtractionResult(
    units=[],
    stats=ExtractionStats(total_units=0),
)
```

Future extractors must raise `ExtractionNoContentError` instead.

## 5. Provider Interface

Replace the current extraction interface in:

```text
backend/app/providers/extraction/interface.py
```

Remove old protocols:

```python
class PDFExtractor(Protocol):
    def extract(self, file_path: str) -> list[RawDocumentUnit]: ...

class DocxExtractor(Protocol):
    def extract(self, file_path: str) -> list[RawDocumentUnit]: ...

class WebExtractor(Protocol):
    def extract(self, url: str) -> list[RawDocumentUnit]: ...
```

Use one shared protocol:

```python
class ContentExtractor(Protocol):
    def extract(self, input_data: ExtractionInput) -> ExtractionResult:
        ...
```

Rules:

- The interface must not depend on python-docx objects.
- The interface must not depend on PyMuPDF objects.
- The interface must not depend on BeautifulSoup or trafilatura objects.
- The interface must not depend on FastAPI upload objects.
- The interface must not depend on database models.
- The interface must not accept local filesystem paths as its shared contract.
- Future DOCX, PDF, and HTML extractors all implement `ContentExtractor`.

## 6. Runtime Extraction Errors

Create runtime extraction errors separately from `SourceError`.

Suggested file:

```text
backend/app/providers/extraction/errors.py
```

Suggested classes:

Each subclass must own a stable error code. Callers should not pass arbitrary
error codes for known error categories.

```python
class ExtractionError(Exception):
    error_code = "extraction_error"

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        details: dict[str, object] | None = None,
    ) -> None:
        ...

class ExtractionParsingError(ExtractionError):
    error_code = "extraction_parsing_failed"

class ExtractionNoContentError(ExtractionError):
    error_code = "extraction_no_content"

class ExtractionSourceTypeMismatchError(ExtractionError):
    error_code = "extraction_source_type_mismatch"

class ExtractionInvariantError(ExtractionError):
    error_code = "extraction_invariant_failed"
```

Rules:

- Runtime exceptions and `SourceError` must remain separate.
- Do not return `SourceError` from provider interfaces.
- Mapping runtime errors to `SourceError` belongs to the future extraction
  service boundary in Phase 2.6.
- Errors must preserve the subclass-owned stable `error_code`.
- Errors must preserve `message`.
- Errors must preserve `retryable`.
- Errors must preserve `details`.
- Do not store or log binary content in error details.
- Use `ExtractionInvariantError`, not `ExtractionValidationError`, to avoid
  confusion with `pydantic.ValidationError`.

Stage mapping later:

| Error type | Future SourceError stage |
| --- | --- |
| DNS, timeout, redirect, HTTP failure | `downloading` |
| Invalid/corrupt DOCX/PDF/HTML or parser cannot open content | `parsing` |
| Parser opened content but no extractable units exist | `extracting` |

Phase 2.1 defines the error types only. It does not implement this mapping.

## 7. Raw Unit ID Helper

Create a deterministic raw unit ID helper.

Suggested file:

```text
backend/app/providers/extraction/ids.py
```

Contract:

```python
def build_raw_unit_id(document_id: str, unit_index: int) -> str:
    return f"raw:{document_id.strip()}:{unit_index:06d}"
```

Rules:

- Reject blank `document_id`.
- Reject negative `unit_index`.
- Do not use UUIDs.
- Do not use content hashes.
- Duplicate content in different positions must still get different
  `raw_unit_id` values.

Examples:

```text
build_raw_unit_id("doc_123", 0) -> "raw:doc_123:000000"
build_raw_unit_id("doc_123", 12) -> "raw:doc_123:000012"
```

## 8. Metadata Naming Conventions

Use snake_case keys in `extra_metadata` and `extractor_config`.

Recommended generic keys:

```text
extractor
extractor_version
parser
parser_version
item_index
block_index
page_index
paragraph_index
table_index
html_tag
source_url
final_url
```

Rules:

- Store parser-native positions in `extra_metadata`.
- Do not promote parser-specific counters to top-level schema fields in Phase
  2.1.
- Do not store raw document content in metadata.
- Do not store secrets, cookies, authorization headers, or credentials in
  metadata.

## 9. Test Plan

Update existing document schema tests:

- Existing `RawDocumentUnit` payload helpers must include `unit_index`.
- `RawDocumentUnit` accepts valid `unit_index`.
- `RawDocumentUnit` rejects missing `unit_index`.
- `RawDocumentUnit` rejects negative `unit_index`.
- Existing derived field tests must still pass.

Add extraction schema tests:

- `ExtractionInput` accepts valid bytes and metadata.
- `ExtractionInput` rejects empty `content_bytes`.
- `ExtractionInput` rejects blank `source_uri` when `source_uri` is provided.
- `ExtractionInput.content_bytes` is excluded from `model_dump()`.
- `ExtractionInput.content_bytes` does not appear in `repr()`.
- `ExtractionInput` rejects unknown fields.
- `FetchedContent` accepts valid bytes and HTTP metadata.
- `FetchedContent` rejects empty `content_bytes`.
- `FetchedContent` requires `status_code`.
- `FetchedContent` rejects status codes outside `100..599`.
- `FetchedContent.content_bytes` is excluded from `model_dump()`.
- `FetchedContent.content_bytes` does not appear in `repr()`.
- `FetchedContent` rejects unknown fields.
- `ExtractionStats.total_units < 1` is rejected.
- `ExtractionStats` rejects negative `skipped_items`.
- `ExtractionWarning` accepts `parsing` and `extracting`.
- `ExtractionWarning` rejects unsupported stages.
- `ExtractionWarning` rejects negative `item_index`.
- `ExtractionWarning` rejects negative `unit_index`.
- `ExtractionResult` accepts valid continuous units.
- `ExtractionResult` rejects empty `units`.
- `ExtractionResult` rejects duplicate `raw_unit_id` values.
- `ExtractionResult` rejects duplicate `unit_index` values.
- `ExtractionResult` rejects non-continuous `unit_index` values.
- `ExtractionResult` rejects list order that does not match `unit_index`.
- `ExtractionResult` rejects mismatched unit `source_id`.
- `ExtractionResult` rejects mismatched unit `document_id`.
- `ExtractionResult` rejects mismatched unit `source_type`.
- `ExtractionResult` rejects `stats.total_units` mismatch.
- `ExtractionResult` rejects `stats.warning_count` mismatch.
- Default list/dict fields are not shared across instances.
- Unknown field rejection is covered for all extraction schemas.

Add provider interface tests:

- Old extraction interfaces no longer import or reference `PDFExtractor`,
  `DocxExtractor`, or `WebExtractor`.
- A fake `ContentExtractor` implementation can return an `ExtractionResult`
  without any parser dependency.

Add ID helper tests:

- `build_raw_unit_id("doc_123", 0)` returns `raw:doc_123:000000`.
- `build_raw_unit_id("doc_123", 12)` returns `raw:doc_123:000012`.
- Blank `document_id` is rejected.
- Negative `unit_index` is rejected.
- Same `document_id` and same `unit_index` always produce the same ID.

Add error tests:

- `ExtractionError` exposes stable `error_code = "extraction_error"`.
- Each known subclass exposes its own stable `error_code`.
- `ExtractionError` preserves `message`.
- `ExtractionError` preserves `retryable`.
- `ExtractionError` preserves `details`.
- Specific subclasses are instances of `ExtractionError`.
- Error details do not require or expose binary content.

Focused verification command:

```bash
cd backend
pytest tests/test_document_schema.py \
       tests/test_extraction_schema.py \
       tests/test_extraction_interface.py \
       tests/test_extraction_errors.py \
       tests/test_extraction_ids.py
```

Full regression verification is also required because adding required
`RawDocumentUnit.unit_index` can break fixtures outside the focused extraction
tests.

```bash
cd backend
pytest
```

## 10. Acceptance Criteria

Phase 2.1 is complete when:

- `RawDocumentUnit` has `unit_index`.
- Extraction core schemas exist and reject unknown fields.
- Binary `content_bytes` is non-empty, excluded from dumps, and hidden from repr.
- Successful `ExtractionResult` cannot contain zero units.
- `ExtractionStats.total_units` cannot be less than `1`.
- `skipped_items` is used instead of `skipped_units`.
- `FetchedContent` has no source/document lineage fields.
- `FetchedContent.status_code` is required.
- `ExtractionInput.source_uri` rejects empty or whitespace-only values when
  provided.
- `media_type` and `status_code` are used consistently.
- `ExtractionWarning.stage` is validated against allowed stages.
- Old file-path and URL-based extraction protocols are removed.
- One shared `ContentExtractor` protocol exists.
- Runtime extraction errors exist separately from `SourceError`.
- Runtime invariant failures use `ExtractionInvariantError`.
- Raw unit ID generation is deterministic and test-covered.
- Focused tests and full backend regression tests pass.
