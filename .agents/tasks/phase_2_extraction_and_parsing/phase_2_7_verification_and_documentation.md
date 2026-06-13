# Phase 2.7: Final Verification and Documentation

Parent phase: `phase_2_source_extraction_overview.md`

Depends on:

* `phase_2_1_extraction_core_contracts.md`
* `phase_2_2_docx_extraction.md`
* `phase_2_3_pdf_extraction.md`
* `phase_2_4_url_fetching.md`
* `phase_2_5_html_extraction.md`
* `phase_2_6_registry_and_extraction_service.md`

## 1. Purpose

Perform the final Phase 2 quality gate before moving into cleaning, chunking,
embedding, indexing, retrieval, or generation.

Phase 2.7 should verify that PDF, DOCX, and URL/HTML extraction all produce
compatible `ExtractionResult -> RawDocumentUnit[]` outputs and document the
real contract that Phase 3 can rely on.

Phase 2.7 is not a feature phase.

---

## 2. Scope

Implement:

* Cross-extractor contract verification.
* Service-level verification after Phase 2.6.
* Final regression test pass.
* Final Phase 2 extraction report.
* Cross-extractor capability matrix for Phase 3.
* Documentation updates in the Phase 2 overview.

Do not implement:

* new parsing behavior;
* new source types;
* cleaning;
* chunking;
* embedding;
* indexing;
* retrieval;
* generation;
* persistence;
* API routes;
* real external network tests.

---

## 3. Verification Goals

Verify that all extraction paths satisfy the same core output contract:

```text
DOCX bytes -> ExtractionService.extract_bytes(...) -> ExtractionResult
PDF bytes  -> ExtractionService.extract_bytes(...) -> ExtractionResult
URL        -> ExtractionService.extract_url(...)   -> ExtractionResult
```

For direct provider tests, also verify:

```text
DocxExtractor.extract(...) -> ExtractionResult
PdfExtractor.extract(...)  -> ExtractionResult
HtmlExtractor.extract(...) -> ExtractionResult
```

Do not require real websites. URL tests must use fake fetchers or mocked HTTPX
transports.

---

## 4. Cross-Extractor Matrix

Add a Phase 2 cross-extractor matrix to the final documentation.

The matrix should describe actual behavior, not aspirational behavior.

Recommended table:

| Contract | DOCX | PDF | HTML |
| --- | --- | --- | --- |
| Produces `ExtractionResult` | Yes | Yes | Yes |
| Produces `RawDocumentUnit[]` | Yes | Yes | Yes |
| `source_uri` preserved | Yes, when provided | Yes, when provided | Yes, final URL from service |
| Deterministic `raw_unit_id` | Yes | Yes | Yes |
| Continuous `unit_index` | Yes | Yes | Yes |
| One UTC timestamp per run | Yes | Yes | Yes |
| Computed metrics/hash | Schema-generated | Schema-generated | Schema-generated |
| Blank units rejected | Yes | Yes | Yes |
| Page range | None | One-based `page_start/page_end` | None |
| Heading lineage | DOCX heading styles | None | Semantic `h1`-`h6` only |
| Table structure | `tsv_escaped_v1` | None | `tsv_escaped_v1` |
| List structure | Paragraph-like text unless present in DOCX body text | None | List item units |
| Network access in extractor | None | None | None |
| Network access in service path | None | None | URL fetcher only |
| Parser-specific metadata | `extra_metadata` | `extra_metadata` | `extra_metadata` |
| No cleaning/chunking | Yes | Yes | Yes |

If implementation details differ by the time Phase 2.7 runs, update the matrix
to match the actual code and tests.

---

## 5. Contract Checks

For each source type, verify:

* `ExtractionResult.source_id` is preserved.
* `ExtractionResult.document_id` is preserved.
* `ExtractionResult.source_type` is correct.
* Every unit lineage matches result lineage.
* Every unit has nonblank `content`.
* Every unit has deterministic `raw_unit_id`.
* `raw_unit_id` values are unique.
* `unit_index` values are unique.
* `unit_index` values are continuous and ordered from `0`.
* `extracted_at` is one common UTC timestamp per extraction run.
* `stats.total_units == len(units)`.
* `stats.warning_count == len(warnings)`.
* computed fields are schema-generated:
  * `character_count`
  * `word_count`
  * `content_hash`
* parser-specific details stay inside `extra_metadata`.
* `content_bytes` does not appear in `model_dump()`, repr, warnings, errors, or
  metadata.

---

## 6. Source-Specific Checks

DOCX:

* Paragraph/table body order is deterministic.
* Heading paths come from DOCX heading styles.
* Blank headings do not update heading state.
* Tables use `tsv_escaped_v1`.
* DOCX does not fabricate page numbers.

PDF:

* Page ranges are one-based.
* `page_start == page_end == page_number`.
* Page/block ordering is deterministic.
* Bbox malformed blocks are skipped with warning.
* Image-only or blank PDFs raise `ExtractionNoContentError`.
* PDF does not fabricate heading paths.

HTML:

* URL/HTML service path preserves final URL as `source_uri`.
* `HtmlExtractor` performs no network calls.
* Root selection behavior is deterministic.
* Ignored semantic containers are not counted as skipped candidates.
* Invalid charset fallback emits warning.
* HTML headings use `content_type=paragraph` and `block_type=heading`.
* List item ownership avoids nested-list duplication.
* Captions and tables are separate candidates.
* HTML tables use `tsv_escaped_v1`.
* HTML does not fabricate page numbers.

URL fetching:

* Fetcher returns `FetchedContent`.
* `content_bytes` is excluded from dumps and repr.
* URL validation, SSRF controls, redirect validation, response size limit,
  deadline, and safe diagnostics remain covered by mocked tests.
* Tests do not call real websites.

---

## 7. Service Checks

After Phase 2.6, verify:

* Registry maps each `SourceType` to the correct extractor.
* Registry does not fetch, parse, persist, or map errors.
* `extract_bytes()` supports PDF and DOCX.
* `extract_bytes()` rejects URL source type.
* `extract_url()` coordinates `UrlFetcher -> HtmlExtractor`.
* Service does not accept FastAPI `UploadFile`.
* Provider dependencies are injected and mockable.
* Reserved metadata keys are rejected.
* Caller metadata cannot overwrite service-owned metadata.
* Provider errors map to `ExtractionServiceError.source_error`.
* `SourceError.error_code`, `retryable`, and `failed_stage` are correct.
* Provider exception is preserved as `__cause__`.

---

## 8. Documentation Updates

Update `phase_2_source_extraction_overview.md` with:

* Phase 2.6 completion status and verification result.
* Phase 2.7 completion status and verification result.
* Final Phase 2 summary.
* Cross-extractor matrix.
* Known limitations that Phase 3 must account for.

Known limitations should include:

* PDF extraction currently has no semantic heading detection.
* DOCX and HTML do not provide page numbers.
* HTML heading lineage depends on semantic heading tags, not class/id heuristics.
* HTML may include structural article-adjacent noise that cleaning must handle.
* URL ingestion supports one public HTML page, not crawling.
* Robots handling remains deferred because Phase 2 does not crawl child links.
* Extracted content remains untrusted input for later cleaning/generation
  boundaries.

---

## 9. Test Plan

Run the full backend test suite:

```text
pytest
```

Add or update tests only when they close a real verification gap.

Recommended focused additions:

* cross-extractor invariant tests;
* service integration tests for DOCX, PDF, and URL/HTML;
* `content_bytes` safety checks for service paths;
* error mapping tests using actual provider error classes;
* metadata reserved-key rejection tests;
* matrix-backed assertions for page range and heading behavior.

Do not add tests that require:

* real websites;
* PostgreSQL;
* Qdrant;
* OpenAI;
* browser automation;
* external credentials.

---

## 10. Acceptance Criteria

Phase 2.7 is complete when:

* Full backend regression passes.
* DOCX, PDF, and URL/HTML service paths produce valid `ExtractionResult`.
* Direct extractors still satisfy their provider contracts.
* The service boundary from Phase 2.6 is verified.
* Cross-extractor matrix is documented with actual behavior.
* Known limitations are documented for Phase 3.
* No feature work is added outside verification/documentation.
* No cleaning, chunking, embedding, indexing, retrieval, generation, API,
  repository, or persistence behavior is added.
