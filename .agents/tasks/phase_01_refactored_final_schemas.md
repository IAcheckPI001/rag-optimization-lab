# Phase 1: Final Refactored Schemas Report

## Summary

Phase 1 backend schemas now define strict, explicit contracts for source intake,
document pipeline units, chunks, retrieval contexts, citations, and query
responses.

The schema layer is designed to support observability and traceability across
the RAG pipeline before implementing actual ingestion, parsing, cleaning,
chunking, embedding, indexing, retrieval, or generation services.

No runtime RAG behavior, provider implementation, database schema, route, or new
dependency is part of this schema refactor.

## Current Schema Files

- `backend/app/schemas/common.py`
- `backend/app/schemas/health.py`
- `backend/app/schemas/source.py`
- `backend/app/schemas/document.py`
- `backend/app/schemas/retrieval.py`
- `backend/app/schemas/generation.py`

## Common Schema Rules

`common.py` defines shared schema primitives.

### `NonEmptyStr`

Used for identifiers, labels, names, hashes, and other important strings that
must not be empty, blank, or null.

Rules:

- Trims surrounding whitespace.
- Requires at least one character after trimming.
- Should not be used for document `content`, because raw parsed/crawled content
  must preserve whitespace exactly.

### `PipelineSchema`

Internal pipeline and query contract schemas inherit from `PipelineSchema`.

Rules:

- Uses Pydantic `extra="forbid"`.
- Unknown fields are rejected.
- Flexible debug/provider-specific values must use `extra_metadata`.

This applies to internal source, document, retrieval, generation, and query
contracts. It does not define external adapter/provider payload models.

## Source Schemas

Source schemas live in `source.py`.

### Purpose

Represent the user-created input source and its processing lifecycle.

Data model direction:

```text
source_id = one user-created input source
            file upload or seed URL
```

### Key Types

- `SourceType`: `pdf`, `docx`, `url`
- `SourceStatus`: `pending`, `processing`, `completed`, `failed`
- `ProcessingStage`: `queued`, `downloading`, `parsing`, `extracting`,
  `cleaning`, `chunking`, `embedding`, `indexing`, `completed`, `failed`
- `SourceError`
- `PdfSourceMetadata`
- `DocxSourceMetadata`
- `UrlSourceMetadata`
- `SourceMetadata`
- `SourceCreateResponse`
- `SourceDetailResponse`

### Important Rules

- `SourceStatus` remains the coarse lifecycle status.
- `ProcessingStage` tracks detailed pipeline progress.
- `SourceDetailResponse.status` is kept.
- `SourceDetailResponse.metadata` is structured source metadata.
- Source metadata is a discriminated union using `metadata_type`.
- Source errors include error code, message, failed stage, and retryability.

### `extra_metadata`

Available on source metadata models for values useful for debug or
observability but not stable enough to become first-class fields.

Examples:

PDF:

```python
extra_metadata={
    "parser": "pymupdf",
    "parser_version": "1.24.x",
    "is_encrypted": False,
    "has_images": True,
}
```

DOCX:

```python
extra_metadata={
    "parser": "python-docx",
    "styles_detected": ["Heading 1", "Normal"],
}
```

URL:

```python
extra_metadata={
    "extractor": "trafilatura",
    "fallback_extractor": "beautifulsoup",
    "redirect_count": 2,
    "response_time_ms": 841,
    "charset": "utf-8",
}
```

## Document Schemas

Document pipeline schemas live in `document.py`.

### Purpose

Represent the transformation lineage from extracted raw content to cleaned
content and final chunks for embedding/retrieval.

Data model direction:

```text
Source -> Document -> RawDocumentUnit -> CleanDocumentUnit -> DocumentChunk
```

Identifier meanings:

- `document_id`: logical document belonging to a source.
- `raw_unit_id`: page, section, or block after extraction.
- `clean_unit_id`: unit after cleaning.
- `chunk_id`: final chunk used for embedding and retrieval.

### Key Types

- `DocumentContentType`
- `DocumentUnitBase`
- `RawDocumentUnit`
- `CleanDocumentUnit`
- `DocumentChunk`

### Content Rules

`content` is a plain `str`, not `NonEmptyStr`.

Rules:

- Preserve raw/clean/chunk content exactly.
- Do not strip or normalize content in schema.
- Reject blank or whitespace-only content.

This allows raw extraction output to remain auditable while still preventing
empty units from entering the pipeline.

### Derived Metrics

`DocumentUnitBase` exposes derived output fields using Pydantic
`computed_field`:

- `character_count`
- `word_count`
- `content_hash`

Rules:

- Caller does not pass these fields.
- Passing them is rejected because schemas are strict.
- Values are derived from the current instance `content`.
- `model_dump()` includes the derived values.
- Raw, clean, and chunk hashes are calculated separately from their own content.
- Hash is not copied from a previous stage.

### Page Range Rules

For document units and chunks:

No page:

```python
page_start = None
page_end = None
```

One page:

```python
page_start = 5
page_end = 5
```

Multiple pages:

```python
page_start = 5
page_end = 6
```

Invalid:

```python
page_start = 5
page_end = None
```

```python
page_start = None
page_end = 5
```

```python
page_start = 6
page_end = 5
```

Page numbers must be positive when provided.

### Cleaning Rules

`CleanDocumentUnit` tracks:

- `raw_unit_id`
- `transformations`
- `original_character_count`
- `removed_character_count`
- `cleaned_at`

Rules:

- `original_character_count` cannot be less than cleaned `character_count`.
- `removed_character_count` is derived when omitted.
- If provided, `removed_character_count` must match
  `original_character_count - character_count`.

### Chunk Rules

`DocumentChunk` tracks:

- `chunk_id`
- `clean_unit_id`
- `chunk_index`
- `start_char`
- `end_char`
- `token_count`
- `chunker_name`
- `chunker_version`
- `created_at`

Rules:

- `chunk_index >= 0`.
- `start_char` and `end_char` may both be `None`.
- If `end_char` is provided, `start_char` is required.
- `end_char` must be greater than `start_char`.
- `token_count` may be `None`, otherwise it must be `>= 1`.

### `extra_metadata`

Available on `DocumentUnitBase` and inherited by raw units, clean units, and
chunks.

Examples:

Raw unit:

```python
extra_metadata={
    "parser": "pymupdf",
    "block_type": "text",
    "block_index": 12,
    "bbox": [72, 120, 500, 180],
}
```

Clean unit:

```python
extra_metadata={
    "before_line_count": 24,
    "after_line_count": 18,
    "removed_boilerplate": True,
}
```

Chunk:

```python
extra_metadata={
    "chunk_size": 800,
    "chunk_overlap": 120,
    "separator_used": "\n\n",
    "split_reason": "paragraph_boundary",
}
```

## Retrieval Schemas

Retrieval schemas live in `retrieval.py`.

### Purpose

Separate stable chunk/source provenance from scoring and ranking details.

Citation should rely on stable chunk snapshot data, not mutable score/rank
fields.

### Key Types

- `RetrievalMethod`
- `RetrievedChunkSnapshot`
- `RetrievedContext`
- `QueryRequest`

### `RetrievedChunkSnapshot`

Contains fixed chunk/source information:

- `chunk_id`
- `clean_unit_id`
- `document_id`
- `source_id`
- `content`
- `content_hash`
- `source_type`
- `source_uri`
- `page_start`
- `page_end`
- `section`
- `heading_path`
- `token_count`
- `extra_metadata`

Rules:

- Important ids, content, and content hash must not be empty, blank, or null.
- Page range follows the same invariant as document units.
- `token_count` may be `None`, otherwise it must be `>= 1`.

### `RetrievedContext`

Contains scoring/ranking details:

- `retrieval_methods`
- `vector_score`
- `keyword_score`
- `metadata_boost`
- `rerank_score`
- `final_score`
- `retrieval_rank`
- `final_rank`
- `selected_for_generation`

Rules:

- `retrieval_methods` must not be empty.
- `retrieval_rank >= 1`.
- `final_rank` may be `None`, otherwise it must be `>= 1`.

### `QueryRequest`

Rules:

- `question` is stripped.
- Blank questions are rejected.
- `question` length is capped.
- `top_k` is bounded.
- Unknown fields are rejected.

## Generation Schemas

Generation schemas live in `generation.py`.

### `Citation`

Compact citation contract:

- `label: NonEmptyStr`
- `chunk_id: NonEmptyStr`
- `quote: NonEmptyStr`

Rules:

- `label` is the display label shown in the answer, for example `[1]`.
- `chunk_id` points to a retrieved context.
- `quote` is the preview snippet from the cited context.

Detailed provenance comes from `QueryResponse.contexts[].chunk`.

### `QueryResponse`

Fields:

- `answer`
- `citations`
- `contexts`
- `insufficient_context`

Validator rules:

- Every citation chunk id must exist in `contexts`.
- Referenced context must have `selected_for_generation = True`.
- Citation quote must be contained in referenced chunk content.
- Citation label must appear directly in `answer`.

This prevents:

- Orphan citations.
- Citations from unused contexts.
- Hallucinated quotes.
- Missing citation labels in the answer text.

## Tests Implemented

Schema tests live under `backend/tests/`.

### Source Tests

File:

- `test_source_schema.py`

Coverage:

- Valid PDF metadata.
- Valid DOCX metadata.
- Valid URL metadata and error.
- Source lifecycle fields.
- Source error validation.
- Empty, blank, null, invalid enum, and invalid datetime cases.
- Unknown field rejection.
- Source metadata `extra_metadata`.

### Document Tests

File:

- `test_document_schema.py`

Coverage:

- Valid raw units, clean units, and chunks.
- Content preservation with whitespace.
- Blank content rejection.
- Derived fields in `model_dump()`.
- Reject derived metrics/hash as input.
- Separate raw/clean/chunk hash derivation.
- Missing required fields.
- Unknown field rejection.
- `extra_metadata` acceptance.
- Page range invariants.
- Page zero/negative rejection.
- Heading path validation.
- Default list/dict isolation.
- Cleaning metric validation.
- Chunk offset validation.
- Token count validation.

### Retrieval Tests

File:

- `test_retrieval_schema.py`

Coverage:

- Valid retrieved chunk snapshot.
- Valid retrieved context.
- Empty, blank, and null required fields.
- Page range validation.
- Heading path validation.
- Token count validation.
- Unknown field rejection.
- Empty and invalid retrieval methods.
- Rank validation.

### Generation Tests

File:

- `test_generation_schemas.py`

Coverage:

- Query request validation.
- Compact citation validation.
- Citation unknown field rejection.
- Query response citation reference validation.
- Unknown chunks.
- Unselected generation contexts.
- Quote not contained in chunk.
- Label missing from answer.
- Query response unknown field rejection.

### Request Tests

File:

- `test_request_schema.py`

Coverage:

- Query request accepts valid input.
- Query question is stripped.
- Blank question rejection.
- Question max length rejection.
- Unknown field rejection.

### Health Tests

File:

- `test_health.py`

Coverage:

- App import smoke test.
- `GET /health` returns `{"status": "ok"}`.

## Latest Verification

Command:

```bash
cd backend
pytest tests/test_source_schema.py tests/test_document_schema.py tests/test_retrieval_schema.py tests/test_generation_schemas.py tests/test_request_schema.py tests/test_health.py
```

Latest result:

```text
122 passed, 1 warning
```

Known warning:

- FastAPI/Starlette TestClient warning about `httpx`.

## Current Data Relationship

The schema lineage now supports this relationship:

```text
Source
  source_id
    -> Document
       document_id
         -> RawDocumentUnit
            raw_unit_id
              -> CleanDocumentUnit
                 clean_unit_id
                   -> DocumentChunk
                      chunk_id
                        -> RetrievedChunkSnapshot
                           -> RetrievedContext
                              -> Citation
```

Cross-object existence checks are not implemented in schema. They should be
implemented later in services/repositories when persistence and pipeline
orchestration exist.

## Deferred Decisions

- Stable id generation strategy.
- Exact tokenizer and token-count calculation method.
- Exact final score formula.
- Metadata boost semantics.
- Whether hybrid retrieval should add a dedicated `hybrid` retrieval method.
- Persistence schema for sources, documents, units, chunks, retrieval logs, and
  citations.
- Citation UI behavior beyond compact schema fields.
