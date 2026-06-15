# Phase 3.7 - Final Verification And Documentation

Status: Planned.

Depends on:

* Phase 3.1 through Phase 3.6 complete.

## Purpose

Verify Phase 3 end to end and document the final cleaning behavior, limitations,
and Phase 4 input contract.

This sub-phase should not add new cleaning behavior except minor fixes required
by verification.

Do not add API routes, persistence, chunking, embedding, indexing, retrieval,
generation, BM25, hybrid retrieval, reranking, crawling, Playwright, or new
dependencies.

## Verification Matrix

Verify the full flow:

```text
DOCX bytes -> ExtractionService -> CleaningService -> CleaningResult
PDF bytes  -> ExtractionService -> CleaningService -> CleaningResult
URL/HTML   -> fake UrlFetcher -> ExtractionService -> CleaningService -> CleaningResult
```

Required checks:

* source/document/type lineage preserved
* raw unit lineage preserved
* clean IDs deterministic and raw-index based
* clean indexes continuous and ordered
* relative raw order preserved
* one cleaned_at per cleaning run
* extracted_at remains extractor-owned
* cleaned_at remains cleaner-owned
* `transformations` stable rule codes only
* no duplicate `applied_rules` metadata
* dropped-unit audit records safe
* stats equations hold
* warnings use `ProcessingStage.cleaning`
* no raw content in errors
* no `content_bytes` in schema dumps or diagnostics
* table/code/list/prose behavior preserved
* ambiguous content preserved

## Cross-Source Expectations

DOCX:

* headings preserved
* heading_path and section preserved
* tables preserve `tsv_escaped_v1`
* short headings/captions preserved
* no fabricated page numbers

PDF:

* page_start/page_end preserved
* bbox metadata preserved
* page-number candidates preserved/warned unless page geometry is available
* no heading inference
* no OCR
* no table reconstruction

HTML:

* document title preserved
* body headings preserved
* title/H1 duplicate text preserved
* heading lineage preserved
* tables preserve `tsv_escaped_v1`
* code indentation preserved
* high-confidence UI noise dropped only by contextual rules
* no domain-specific selector rules
* no crawling
* no JavaScript rendering

## Smoke Scripts

Add or update smoke scripts only if useful and deterministic:

```text
backend/scripts/smoke_test_cleaning_docx.py
backend/scripts/smoke_test_cleaning_pdf.py
backend/scripts/smoke_test_cleaning_html.py
```

Rules:

* no external websites
* use in-memory or local fixtures
* do not require PostgreSQL, Qdrant, OpenAI, or network
* print safe summary only:
  * source type
  * input unit count
  * output unit count
  * dropped count
  * warning count
  * transformation counters
* do not print full documents

Smoke scripts are optional if pytest coverage is already sufficient.

## Documentation To Add Or Update

Create or update within the Phase 3 task directory only unless explicitly
approved:

```text
.agents/tasks/phase_3_cleaning_and_normalization/phase_3_completion_report.md
```

Suggested report sections:

* implemented files
* final contracts
* contract changes from pre-Phase 3 state
* known conflicts resolved
* cleaning rule behavior
* dropped-unit reason codes
* warning codes
* source-specific behavior matrix
* resource limits
* error mapping
* tests run
* known limitations
* Phase 4 input contract

Do not rewrite broader architecture docs unless requested.

## Phase 4 Input Contract

Document that Phase 4 should consume:

```text
CleaningResult.units: list[CleanDocumentUnit]
```

Phase 4 can rely on:

* non-empty successful unit list
* `clean_unit_id`
* `clean_unit_index`
* `raw_unit_id`
* `document_id`
* `source_id`
* `source_type`
* `source_uri`
* `content`
* page/section/heading metadata when present
* `content_type`
* parser metadata in `extra_metadata`
* cleaning metadata in `extra_metadata["cleaning"]`
* `transformations`
* schema-computed `content_hash`, `character_count`, `word_count`

Phase 4 must not need to understand:

* PyMuPDF objects
* python-docx objects
* BeautifulSoup objects
* HTTPX responses
* URL fetching internals
* source-specific parser implementation details

## Test Commands

Focused Phase 3 suite:

```text
python -m pytest tests/test_cleaning_schema.py tests/test_cleaning_errors.py tests/test_cleaning_ids.py tests/test_cleaning_interface.py tests/test_cleaning_normalization.py tests/test_rule_based_cleaner_construction.py tests/test_cleaning_source_filters.py tests/test_cleaning_deduplication.py tests/test_cleaning_service.py
```

Phase 2 regression:

```text
python -m pytest tests/test_extraction_schema.py tests/test_extraction_errors.py tests/test_extraction_ids.py tests/test_extraction_interface.py tests/test_docx_extractor.py tests/test_pdf_extractor.py tests/test_html_extractor.py tests/test_url_fetcher.py tests/test_extraction_service.py
```

Schema regression:

```text
python -m pytest tests/test_document_schema.py tests/test_source_schema.py tests/test_retrieval_schema.py tests/test_generation_schemas.py tests/test_request_schema.py
```

Full backend regression:

```text
python -m pytest
```

## Acceptance Criteria

Phase 3 is complete only when:

* all Phase 3 focused tests pass
* Phase 2 regression tests pass
* full backend regression passes
* DOCX, PDF, and URL/HTML service paths produce valid `CleaningResult`
* no tests call real external services
* no raw content leaks into errors
* no new dependencies were added
* no post-MVP retrieval/reranking/crawling features were added
* final completion report exists
* Phase 4 input contract is documented

## Known Limitations To Preserve In Documentation

Phase 3 does not solve:

* missing JavaScript-rendered HTML
* full website crawling
* private/authenticated/paywalled pages
* PDF OCR
* PDF reading order errors
* PDF table reconstruction
* PDF heading inference
* semantic boilerplate classification
* prompt-injection removal
* near-duplicate detection
* domain-specific scraping rules
* spell correction
* summarization
* translation

These limitations should be explicit rather than hidden behind aggressive
cleaning.

