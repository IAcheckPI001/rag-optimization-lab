# Phase 1: Refactored Source Schemas

## Goal

Refine the Phase 1 source schemas so the backend can represent source lifecycle,
fine-grained processing progress, source-specific metadata, and ingestion errors
before implementing actual ingestion, crawling, parsing, indexing, or storage.

This task updates schema contracts only. It must not implement external
infrastructure, file upload endpoints, URL fetching, parsing, cleaning,
chunking, embedding, indexing, retrieval, generation, or persistence.

---

## Relevant Instructions

Before implementation, read:

- `AGENTS.md`
- `backend/AGENTS.md`
- `.agents/architecture.md`
- `tests/AGENTS.md`
- `backend/tests/AGENTS.md`

This task changes schema/API contracts, so keep the change scoped and add focused
tests.

---

## Fixed Decisions

- Keep `SourceStatus` as the coarse lifecycle status.
- Add `ProcessingStage` as the fine-grained progress state.
- Keep `SourceDetailResponse.status: SourceStatus`.
- Use Pydantic `BaseModel`; do not introduce a shared `StrictSchema` base class.
- Use `datetime` for `created_at` and all future date/time fields.
- Do not add dependencies.
- Do not change database schema.
- Do not add provider implementations.

---

## Schema Changes

Update `backend/app/schemas/source.py`.

### `ProcessingStage`

Add:

```python
class ProcessingStage(str, Enum):
    queued = "queued"
    downloading = "downloading"
    parsing = "parsing"
    extracting = "extracting"
    cleaning = "cleaning"
    chunking = "chunking"
    embedding = "embedding"
    indexing = "indexing"
    completed = "completed"
    failed = "failed"
```

Use this field to represent the detailed phase of source processing. This does
not replace `SourceStatus`.

### `SourceError`

Add:

```python
class SourceError(BaseModel):
    error_code: str
    message: str
    failed_stage: ProcessingStage
    retryable: bool = False
```

Validation requirements:

- `error_code` must not be empty, blank, or null.
- `message` must not be empty, blank, or null.
- `failed_stage` must be a valid `ProcessingStage` and must not be null.

Example error code:

```text
URL_HTTP_403
```

### Source Metadata

Add source-specific metadata models.

```python
class BaseFileMetadata(BaseModel):
    title: str | None = None
    original_filename: str
    checksum_sha256: str | None = None
```

Validation requirements:

- `original_filename` must not be empty, blank, or null.

```python
class PdfSourceMetadata(BaseFileMetadata):
    metadata_type: Literal["pdf"] = "pdf"
    mime_type: str = "application/pdf"
    total_pages: int | None = None
```

```python
class DocxSourceMetadata(BaseFileMetadata):
    metadata_type: Literal["docx"] = "docx"
    mime_type: str = (
        "application/vnd.openxmlformats-officedocument"
        ".wordprocessingml.document"
    )
    paragraph_count: int | None = None
    table_count: int | None = None
```

```python
class UrlSourceMetadata(BaseModel):
    metadata_type: Literal["url"] = "url"

    original_url: str
    final_url: str | None = None
    canonical_url: str | None = None

    domain: str
    site_name: str | None = None
    title: str | None = None
    description: str | None = None

    language: str | None = None
    author: str | None = None

    published_at: datetime | None = None
    updated_at: datetime | None = None
    crawled_at: datetime | None = None

    http_status: int | None = None
    mime_type: str | None = None
```

Validation requirements:

- `original_url` must not be empty, blank, or null.
- `domain` must not be empty, blank, or null.

Add the discriminated union:

```python
SourceMetadata = Annotated[
    PdfSourceMetadata | DocxSourceMetadata | UrlSourceMetadata,
    Field(discriminator="metadata_type"),
]
```

### `SourceDetailResponse`

Update `SourceDetailResponse` to include:

```python
class SourceDetailResponse(BaseModel):
    source_id: str
    source_type: SourceType
    status: SourceStatus
    display_name: str | None = None
    current_stage: ProcessingStage
    input_uri: str | None = None
    source_uri: str | None = None
    canonical_uri: str | None = None
    created_at: datetime
    error: SourceError | None = None
    metadata: SourceMetadata | None = None
    original_filename: str | None = None
```

Validation requirements:

- `source_id` must not be empty, blank, or null.
- `source_type` must be a valid `SourceType`.
- `status` must be a valid `SourceStatus`.
- `current_stage` must be a valid `ProcessingStage` and must not be null.
- `created_at` must be a valid `datetime` and must not be null.

Keep `original_filename` for Phase 1 compatibility, even though file metadata
also carries `original_filename`.

---

## Out Of Scope

Do not implement:

- File upload endpoints.
- PDF or DOCX extraction.
- URL fetching or crawling.
- URL validation or SSRF protection.
- Cleaning.
- Chunking.
- Embedding calls.
- Qdrant integration.
- PostgreSQL integration.
- Indexing.
- Retrieval.
- Answer generation.
- Citation formatting.
- Retrieval logging persistence.
- Evaluation.
- Database schema or migrations.
- New dependencies.

---

## Testing Requirements

Add or update tests under `backend/tests/`.

Create focused schema tests using fake data only. Tests must not call external
services or infrastructure.

Required cases:

1. Valid PDF source detail with `PdfSourceMetadata`.
2. Valid DOCX source detail with `DocxSourceMetadata`.
3. Valid URL source detail with `UrlSourceMetadata`.
4. Valid source error with `error_code`, `message`, `failed_stage`, and default
   `retryable = False`.
5. Reject empty or blank `source_id`.
6. Reject null `current_stage`.
7. Reject null `created_at`.
8. Reject empty or blank file `original_filename`.
9. Reject empty or blank URL `original_url`.
10. Reject empty or blank URL `domain`.
11. Reject empty or blank `SourceError.error_code`.
12. Reject empty or blank `SourceError.message`.
13. Reject null `SourceError.failed_stage`.
14. Reject invalid enum values such as unsupported `source_type`.
15. Reject invalid datetime input for `created_at`.

Run:

```bash
cd backend
pytest tests/test_source_schema.py tests/test_health.py
```

---

## Acceptance Criteria

The task is complete when:

- `ProcessingStage` exists with all required values.
- `SourceError` exists and validates required fields.
- PDF, DOCX, and URL metadata schemas exist.
- `SourceMetadata` is a discriminated union on `metadata_type`.
- `SourceDetailResponse` includes lifecycle status, detailed processing stage,
  URIs, `created_at`, optional error, optional metadata, and compatibility
  `original_filename`.
- Important raw source fields reject empty, blank, null, or invalid values.
- Tests cover normal, edge, and failure cases.
- Relevant tests pass.
- No out-of-scope behavior or dependency is added.

---

## Required Completion Report

After implementation, report:

1. Summary of schema changes.
2. Created or changed files.
3. Tests added.
4. Verification commands and results.
5. Any deferred schema decisions.
