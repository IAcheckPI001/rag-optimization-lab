# Phase 1: Refactored Schemas Report

## Goal

Refine the Phase 1 schemas so the backend can represent source lifecycle,
document pipeline units, chunk observability, retrieval scoring details, compact
citations, and response-level citation validation before implementing actual
ingestion, crawling, parsing, indexing, retrieval, generation, or persistence.

This task updates schema contracts only. It must not implement external
infrastructure, file upload endpoints, URL fetching, parsing, cleaning,
chunking, embedding, indexing, retrieval, generation, or persistence.

---

## Relevant Instructions

Before implementation, read:

- `AGENTS.md`
- `backend/AGENTS.md`
- `.agents/architecture.md`
- `.agents/rag-pipeline.md`
- `tests/AGENTS.md`
- `backend/tests/AGENTS.md`

This task changes schema/API contracts, so keep the change scoped and add focused
tests.

---

## Fixed Decisions

- Keep `SourceStatus` as the coarse source lifecycle status.
- Add `ProcessingStage` as the fine-grained source progress state.
- Keep `SourceDetailResponse.status: SourceStatus`.
- Use Pydantic `BaseModel`; do not introduce a shared `StrictSchema` base class.
- Use `datetime` for `created_at` and all date/time schema fields.
- Use one shared `NonEmptyStr` type from `backend/app/schemas/common.py`.
- Keep citation labels as display labels, for example `[1]`.
- Keep citation details compact; detailed provenance lives in retrieved contexts.
- Do not add dependencies.
- Do not change database schema.
- Do not add provider implementations.

---

## Common Schema Utilities

Create `backend/app/schemas/common.py`.

```python
NonEmptyStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]
```

Use this shared type anywhere an important string must not be empty, blank, or
null.

Applied areas:

- Source identifiers and source metadata.
- Document unit identifiers and content.
- Chunk identifiers and chunker metadata.
- Retrieved chunk snapshots.
- Citation labels, chunk ids, and quotes.

---

## Source Schema Changes

Update `backend/app/schemas/source.py`.

### `ProcessingStage`

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

```python
class SourceError(BaseModel):
    error_code: NonEmptyStr
    message: NonEmptyStr
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

Add source-specific metadata models:

- `BaseFileMetadata`
- `PdfSourceMetadata`
- `DocxSourceMetadata`
- `UrlSourceMetadata`
- `SourceMetadata`

Important validation requirements:

- File `original_filename` must not be empty, blank, or null.
- URL `original_url` must not be empty, blank, or null.
- URL `domain` must not be empty, blank, or null.
- `SourceMetadata` must be a discriminated union on `metadata_type`.

### `SourceDetailResponse`

`SourceDetailResponse` must include:

- `source_id: NonEmptyStr`
- `source_type: SourceType`
- `status: SourceStatus`
- `display_name: str | None`
- `current_stage: ProcessingStage`
- `input_uri: str | None`
- `source_uri: str | None`
- `canonical_uri: str | None`
- `created_at: datetime`
- `error: SourceError | None`
- `metadata: SourceMetadata | None`

Validation requirements:

- `source_id` must not be empty, blank, or null.
- `source_type` must be valid.
- `status` must be valid.
- `current_stage` must be valid and not null.
- `created_at` must be a valid `datetime` and not null.

---

## Document Schema Changes

Update `backend/app/schemas/document.py`.

### `DocumentContentType`

```python
class DocumentContentType(str, Enum):
    page = "page"
    section = "section"
    paragraph = "paragraph"
    table = "table"
    list = "list"
    code = "code"
    unknown = "unknown"
```

### `DocumentUnitBase`

Add a shared base for raw units, clean units, and chunks.

Important fields:

- `document_id: NonEmptyStr`
- `source_id: NonEmptyStr`
- `source_type: SourceType`
- `source_uri: str | None`
- `content: NonEmptyStr`
- `page_start: int | None = Field(default=None, ge=1)`
- `page_end: int | None = Field(default=None, ge=1)`
- `section: str | None`
- `heading_path: list[NonEmptyStr]`
- `content_type: DocumentContentType`
- `character_count: int = Field(ge=0)`
- `word_count: int | None = Field(default=None, ge=0)`
- `content_hash: NonEmptyStr`
- `metadata: dict[str, object]`

Validator requirements:

- `page_start` is required when `page_end` is provided.
- `page_end` must be greater than or equal to `page_start`.
- `character_count` must match `len(content)`.
- `word_count`, when provided, must match `len(content.split())`.
- `content_hash` must match `sha256(content.encode("utf-8")).hexdigest()`.

### `RawDocumentUnit`

Add:

- `raw_unit_id: NonEmptyStr`
- `extracted_at: datetime`

### `CleanDocumentUnit`

Add:

- `clean_unit_id: NonEmptyStr`
- `raw_unit_id: NonEmptyStr`
- `transformations: list[NonEmptyStr]`
- `original_character_count: int = Field(ge=0)`
- `removed_character_count: int | None = Field(default=None, ge=0)`
- `cleaned_at: datetime`

Validator requirements:

- `original_character_count` cannot be less than cleaned `character_count`.
- `removed_character_count`, when provided, must equal
  `original_character_count - character_count`.
- `removed_character_count` is derived when omitted.

### `DocumentChunk`

Add:

- `chunk_id: NonEmptyStr`
- `clean_unit_id: NonEmptyStr`
- `chunk_index: int = Field(ge=0)`
- `start_char: int | None = Field(default=None, ge=0)`
- `end_char: int | None = Field(default=None, ge=0)`
- `token_count: int | None`
- `chunker_name: NonEmptyStr`
- `chunker_version: str | None`
- `created_at: datetime`

Validator requirements:

- `start_char` is required when `end_char` is provided.
- `end_char` must be greater than `start_char`.
- `chunk_index` must be zero or greater.
- `clean_unit_id`, `chunker_name`, and `created_at` are required.

---

## Retrieval Schema Changes

Update `backend/app/schemas/retrieval.py`.

### `RetrievalMethod`

Add:

- `vector`
- `keyword`
- `metadata`
- `rerank`

These values define retrieval contract options only. Do not implement BM25,
hybrid retrieval, metadata boosting, or reranking in this task.

### `RetrievedChunkSnapshot`

Add a stable chunk/source snapshot for citation and retrieval observability.

Important fields:

- `chunk_id: NonEmptyStr`
- `clean_unit_id: NonEmptyStr | None`
- `document_id: NonEmptyStr`
- `source_id: NonEmptyStr`
- `content: NonEmptyStr`
- `content_hash: NonEmptyStr`
- `source_type: SourceType`
- `source_uri: str | None`
- `page_start: int | None = Field(default=None, ge=1)`
- `page_end: int | None = Field(default=None, ge=1)`
- `section: str | None`
- `heading_path: list[NonEmptyStr]`
- `token_count: int | None = Field(default=None, ge=0)`

Validator requirements:

- `page_start` is required when `page_end` is provided.
- `page_end` must be greater than or equal to `page_start`.
- Important ids, `content`, and `content_hash` must not be empty, blank, or null.

### `RetrievedContext`

Refactor retrieval results into:

- `chunk: RetrievedChunkSnapshot`
- `retrieval_methods: list[RetrievalMethod] = Field(min_length=1)`
- `vector_score: float | None`
- `keyword_score: float | None`
- `metadata_boost: float | None`
- `rerank_score: float | None`
- `final_score: float`
- `retrieval_rank: int = Field(ge=1)`
- `final_rank: int | None = Field(default=None, ge=1)`
- `selected_for_generation: bool = False`

Purpose:

- Keep citation provenance in `chunk`.
- Keep retrieval/ranking/scoring details separate.
- Allow future hybrid/reranking observability without changing the response
  shape.

---

## Generation Schema Changes

Update `backend/app/schemas/generation.py`.

### `Citation`

Use compact citations:

```python
class Citation(BaseModel):
    label: NonEmptyStr
    chunk_id: NonEmptyStr
    quote: NonEmptyStr
```

`label` is the display label that appears in the answer text, for example
`[1]`. Detailed citation provenance is resolved from `contexts[].chunk`.

### `QueryResponse`

Add a response-level validator to ensure citation consistency.

Validator requirements:

- Every `citation.chunk_id` must exist in `contexts`.
- The referenced context must have `selected_for_generation = True`.
- `citation.quote` must be contained in the referenced chunk content.
- `citation.label` must appear directly in `answer`.

This prevents orphan citations, hallucinated quotes, and labels that are missing
from the answer text.

---

## Out Of Scope

Do not implement:

- File upload endpoints.
- PDF or DOCX extraction.
- URL fetching or crawling.
- URL validation or SSRF protection.
- Cleaning implementation.
- Chunking implementation.
- Embedding calls.
- Qdrant integration.
- PostgreSQL integration.
- Indexing.
- Retrieval logic.
- BM25 or hybrid retrieval.
- Reranking.
- Answer generation.
- Citation formatting logic beyond schema validation.
- Retrieval logging persistence.
- Evaluation.
- Database schema or migrations.
- New dependencies.

---

## Testing Requirements

Add or update tests under `backend/tests/`.

Create focused schema tests using fake data only. Tests must not call external
services or infrastructure.

Required test files:

- `tests/test_source_schema.py`
- `tests/test_document_schema.py`
- `tests/test_retrieval_schema.py`
- `tests/test_generation_schemas.py`

Required coverage:

- Valid source metadata for PDF, DOCX, and URL.
- Source error validation.
- Source lifecycle and processing-stage validation.
- Valid raw document units, clean document units, and chunks.
- Document content count/hash validation.
- Page range validation.
- Cleaning metric validation.
- Chunk offset validation.
- Valid retrieved chunk snapshots and retrieved contexts.
- Retrieval method and rank validation.
- Compact citation validation.
- QueryResponse citation-reference validation.
- Reject empty, blank, null, or invalid important fields.

Suggested command:

```bash
cd backend
pytest tests/test_source_schema.py tests/test_document_schema.py tests/test_retrieval_schema.py tests/test_generation_schemas.py tests/test_health.py
```

---

## Acceptance Criteria

The task is complete when:

- `NonEmptyStr` is defined once in `schemas/common.py`.
- Source schemas capture lifecycle, processing stage, source errors, and
  source-specific metadata.
- Document schemas capture raw/clean/chunk lineage, content type, heading path,
  page ranges, content metrics, content hash, cleaning metrics, chunk offsets,
  token count, chunker metadata, and timestamps.
- Retrieval schemas separate stable chunk provenance from scoring/ranking data.
- Citation schema is compact and uses display labels.
- QueryResponse validates citation references against selected generation
  contexts.
- Important schema fields reject empty, blank, null, or invalid values.
- Tests cover normal, edge, and failure cases.
- Relevant tests pass.
- No out-of-scope behavior or dependency is added.

---

## Required Completion Report

After implementation, report:

1. Summary of schema changes.
2. Created or changed files.
3. Tests added or updated.
4. Verification commands and results.
5. Any deferred schema decisions.

Deferred decisions may include:

- Stable id generation strategy.
- Exact token counting method.
- Exact final score formula.
- Metadata boost semantics.
- Whether hybrid retrieval should add a `hybrid` retrieval method.
- Citation UI behavior beyond compact schema fields.
