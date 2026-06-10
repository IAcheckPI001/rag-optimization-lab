# Phase 2: Source Extraction and Parsing

## 1. Purpose of Phase 2

Phase 2 implements the extraction layer that converts DOCX files, PDF files,
and one public website URL into standardized `RawDocumentUnit` objects.

This phase is responsible for:

* Receiving source content that has already been uploaded, loaded, or fetched.
* Reading and parsing the source structure.
* Preserving original document order as extraction provenance.
* Collecting parser metadata, warnings, and extraction statistics.
* Normalizing all outputs into the Phase 1 schemas.
* Reporting extraction errors without implementing later pipeline steps.

Phase 2 does not implement:

* Content cleaning.
* Header, footer, or boilerplate removal through a cleaning pipeline.
* Chunking.
* Tokenization.
* Embedding.
* Indexing.
* Retrieval.
* Answer generation.
* Database persistence.
* API routes.
* OCR.
* JavaScript rendering.
* Multi-page website crawling.

---

## 2. Output of Phase 2

The main output is:

```text
ExtractionResult
  source_id
  document_id
  source_type
  extractor_name
  extractor_version
  units: list[RawDocumentUnit]
  warnings: list[ExtractionWarning]
  stats: ExtractionStats
```

Every extractor must return the same output type:

```text
DOCX bytes -> DocxExtractor -> ExtractionResult
PDF bytes  -> PdfExtractor  -> ExtractionResult
HTML bytes -> HtmlExtractor -> ExtractionResult
```

Each `RawDocumentUnit` must:

* Include `source_id`, `document_id`, `source_type`, `raw_unit_id`, and
  `unit_index`.
* Contain non-empty content while preserving the parser-produced content value.
* Preserve output document order through `unit_index`.
* Include a page range when the source provides reliable page numbers.
* Include section and heading path information when detectable.
* Store parser-specific provenance in `extra_metadata`.
* Not receive `character_count`, `word_count`, or `content_hash` from the
  extractor.
* Allow the schema to derive `character_count`, `word_count`, and
  `content_hash` from `content`.

---

## 3. Raw Unit Ordering and ID Rules

`RawDocumentUnit` must include:

```text
unit_index: int
```

`unit_index` means the order of units returned by the extractor:

* It starts at `0`.
* It is continuous: `0, 1, 2, ...`.
* It represents output order, not necessarily the parser's original block
  position.
* It is added only to `RawDocumentUnit`, not to `DocumentUnitBase`.
* `CleanDocumentUnit` and later stages may define their own ordering rules in
  their own phases.

Parser-native positions should be stored in `extra_metadata`.

Example:

```text
DOCX block 0: heading    -> unit_index 0
DOCX block 1: blank      -> skipped
DOCX block 2: paragraph  -> unit_index 1

RawDocumentUnit:
  unit_index = 1
  extra_metadata = {"block_index": 2}
```

`raw_unit_id` must use this deterministic format:

```text
raw:{document_id}:{unit_index:06d}
```

Example:

```text
raw:doc_123:000000
```

Determinism contract:

* The same input bytes, `document_id`, extractor version, and extractor
  configuration must produce the same output ordering and the same
  `raw_unit_id` values.
* Do not use UUIDs for `raw_unit_id`.
* Do not use content hashes for `raw_unit_id`; duplicate content can appear in
  different document positions.

---

## 4. Extraction Schemas

Create the Phase 2 extraction schemas in:

```text
backend/app/schemas/extraction.py
```

Required schemas:

* `ExtractionInput`
* `ExtractionResult`
* `ExtractionWarning`
* `ExtractionStats`
* `FetchedContent`

`ExtractionInput` should carry source identity, document identity, source type,
content bytes, and safe parser configuration metadata. It must not expose
FastAPI upload objects, parser objects, database records, or local filesystem
paths as part of the shared contract.

`ExtractionStats` should stay intentionally small in Phase 2:

```text
ExtractionStats
  total_units
  skipped_units
  warning_count
  extra_metadata
```

Parser-specific stats such as page counts, table counts, paragraph counts,
HTML tag counts, or parser-specific counters belong in `extra_metadata` unless
they become stable cross-extractor fields in a later phase.

`ExtractionResult` must validate aggregate invariants:

* `units` is not empty.
* `raw_unit_id` values are unique.
* `unit_index` values are unique.
* `unit_index` values are continuous from `0`.
* The list order of `units` matches `unit_index`.
* Every unit has the same `source_id` as the result.
* Every unit has the same `document_id` as the result.
* Every unit has the same `source_type` as the result.
* `stats.total_units == len(units)`.
* `stats.warning_count == len(warnings)`.

These checks are internal extraction aggregate invariants. They do not validate
database existence and should not require repositories.

---

## 5. Architectural Principles

Use one shared extraction contract:

```text
ContentExtractor.extract(
    ExtractionInput
) -> ExtractionResult
```

Implementations:

```text
DocxExtractor
PdfExtractor
HtmlExtractor
```

The provider interface should live under the backend provider boundary, for
example:

```text
backend/app/providers/extraction/interface.py
```

The interface must not depend directly on:

* `python-docx` objects.
* PyMuPDF objects.
* BeautifulSoup or trafilatura objects.
* FastAPI upload objects.
* Local filesystem paths.
* Database models.

Extractors should receive `content_bytes` through `ExtractionInput` so they can
work with:

* Uploaded files.
* Local test fixtures.
* Object storage.
* URL response bodies.
* Background processing workflows.

URL fetching and HTML extraction must remain separate responsibilities:

```text
URL
 -> UrlFetcher
 -> FetchedContent
 -> HtmlExtractor
 -> ExtractionResult
```

In Phase 2, `SourceType.URL` supports only one public HTML page.

---

## 6. Error and Warning Mapping

Runtime exceptions and the `SourceError` schema must remain separate.

The extraction service should map runtime failures to `SourceError` only at the
workflow boundary.

| Failure type | Processing stage |
| --- | --- |
| DNS failure, timeout, redirect failure, HTTP failure | `downloading` |
| Invalid DOCX/PDF, corrupted file, unsupported encoding, parser cannot open content | `parsing` |
| Parser opened successfully but cannot produce units or finds no extractable content | `extracting` |
| Non-fatal skipped block, unsupported image, malformed table | `ExtractionWarning` |

Warnings are non-fatal and should be returned in `ExtractionResult.warnings`.

---

## 7. Dependency Policy

Add parser and fetcher dependencies only when their sub-phase starts.

Phase 2.1:

* No new parser or HTTP dependency.

Phase 2.2:

* Add `python-docx` for DOCX parsing.

Phase 2.3:

* Add `PyMuPDF` for PDF parsing.

Phase 2.4:

* Add `httpx` as a runtime dependency for URL fetching.

Phase 2.5:

* Add `beautifulsoup4` for structural HTML parsing.
* Add `trafilatura` only when it is actually used for main-content detection or
  fallback support.

For each dependency addition:

* State the purpose.
* Follow the existing `pyproject.toml` dependency style.
* Add a minimal import smoke test.
* Do not add a second alternative library unless the implementation uses it.

---

## 8. Phase 2 Breakdown

### Implementation Status

| Sub-phase | Status | Notes |
| --- | --- | --- |
| Phase 2.1 - Extraction Core Contracts | Completed | Implemented core extraction schemas, `RawDocumentUnit.unit_index`, shared `ContentExtractor` protocol, extraction runtime errors, raw unit ID helper, and focused validation tests. Full backend regression passed: `170 passed, 1 warning`. |
| Phase 2.2 - DOCX Extraction | Not started | Parser implementation and dependency addition are deferred to Phase 2.2. |
| Phase 2.3 - PDF Extraction | Not started | Parser implementation and dependency addition are deferred to Phase 2.3. |
| Phase 2.4 - URL Fetching | Not started | Fetcher implementation and SSRF-safe HTTP handling are deferred to Phase 2.4. |
| Phase 2.5 - HTML Extraction | Not started | HTML parser implementation and dependency addition are deferred to Phase 2.5. |
| Phase 2.6 - Extractor Registry and Extraction Service | Not started | Service orchestration and runtime error mapping are deferred to Phase 2.6. |
| Phase 2.7 - Final Verification and Documentation | Not started | Final cross-extractor verification is deferred until extractors exist. |

## Phase 2.1 - Extraction Core Contracts

Status: Completed.

Completion notes:

* Added the shared extraction contracts in `backend/app/schemas/extraction.py`.
* Added `unit_index` to `RawDocumentUnit`.
* Replaced file-path and URL-based extraction protocols with the shared
  `ContentExtractor` protocol.
* Added extraction runtime error types separately from `SourceError`.
* Added deterministic `raw_unit_id` helper.
* Added focused tests for extraction schemas, interface, errors, IDs, and
  updated document schema behavior.
* Verification completed with full backend regression:
  `170 passed, 1 warning`.

### Scope

* Create `backend/app/schemas/extraction.py`.
* Create `ExtractionInput`.
* Create `ExtractionResult`.
* Create `ExtractionWarning`.
* Create `ExtractionStats`.
* Create `FetchedContent`.
* Add `unit_index` to `RawDocumentUnit`.
* Create the `ContentExtractor` protocol.
* Create runtime extraction exceptions.
* Define the `raw_unit_id` generation helper or rule.
* Define output ordering rules.
* Define `extra_metadata` key naming conventions.

### Notes

* The interface must support DOCX, PDF, and HTML.
* Do not expose parser-specific objects in the shared contract.
* Do not add cleaning or chunking fields.
* Binary content must not be serialized into logs or responses.
* Runtime exceptions and the `SourceError` schema must remain separate.
* ID generation must be deterministic and testable.
* Do not add parser dependencies in Phase 2.1.

### Output

* Shared extraction contracts.
* Shared extraction error types.
* Contract and validation tests.

---

## Phase 2.2 - DOCX Extraction

### Scope

* Add `python-docx`.
* Read DOCX content from bytes using `python-docx`.
* Iterate through paragraphs and tables in the original document order.
* Detect headings from paragraph styles.
* Build `heading_path`.
* Extract paragraph text.
* Serialize tables into a stable text format.
* Skip empty or whitespace-only blocks.
* Create one `RawDocumentUnit` for each valid block.
* Collect warnings and extraction statistics.

### Typical Metadata

```text
parser
block_type
block_index
paragraph_index
table_index
style_name
heading_level
row_count
column_count
serialization_format
```

### Notes

* Do not process all paragraphs first and all tables afterward.
* Paragraph and table order must match the original DOCX structure.
* DOCX does not provide reliable page numbers.
* `page_start` and `page_end` should normally be `None`.
* Do not process OCR, images, charts, text boxes, or embedded objects.
* Do not attempt to reconstruct complex list numbering in the first version.

### Output

* `DocxExtractor`.
* DOCX fixtures.
* Tests for paragraphs, headings, nested heading paths, tables, empty content,
  invalid DOCX files, deterministic `unit_index`, and deterministic
  `raw_unit_id`.

---

## Phase 2.3 - PDF Extraction

### Scope

* Add `PyMuPDF`.
* Read PDF content from bytes using PyMuPDF.
* Iterate through pages in order.
* Extract text blocks in a reasonable reading order.
* Create `RawDocumentUnit` objects by page or text block.
* Store page ranges.
* Store block indexes and bounding boxes.
* Detect invalid PDFs and PDFs without extractable text.
* Collect warnings and extraction statistics.

### Typical Metadata

```text
parser
page_index
block_index
block_type
bbox
font_information
rotation
```

### Notes

* Output page numbers must start from `1`.
* Do not implement OCR for scanned PDFs in Phase 2.
* Do not automatically remove headers or footers.
* Do not merge pages or blocks using cleaning heuristics.
* PDF reading order may be imperfect.
* Initial tests should focus on simple-layout PDF fixtures.
* Password-protected or corrupted PDFs must return clear domain errors.

### Output

* `PdfExtractor`.
* PDF fixtures.
* Tests for multi-page documents, blank pages, text block order, invalid PDFs,
  empty extracted content, deterministic `unit_index`, deterministic
  `raw_unit_id`, and valid page ranges.

---

## Phase 2.4 - URL Fetching

### Scope

* Add `httpx` as a runtime dependency.
* Create `UrlFetcher` separately from `HtmlExtractor`.
* Allow only public HTTP and HTTPS URLs.
* Configure request timeouts.
* Limit redirects.
* Validate HTTP response status.
* Validate response content type.
* Limit response size.
* Return `FetchedContent` with final URL, HTML bytes, charset, and HTTP
  metadata.

### Security Requirements

`httpx` does not solve SSRF by itself. `UrlFetcher` must implement:

* Scheme allowlist: `http`, `https`.
* Host validation.
* DNS/IP resolution validation.
* Blocking loopback, private, link-local, reserved, and cloud metadata IPs.
* Revalidation after every redirect target.
* Redirect limit.
* Response-size limit.
* Content-type validation.

### Notes

* Do not allow private, localhost, or internal network URLs.
* Protect against SSRF.
* Do not support login, authenticated sessions, or cookies.
* Do not support JavaScript-rendered websites.
* Do not crawl child links.
* URLs returning PDF or DOCX are outside the initial Phase 2 scope.
* Only HTML responses are supported in the first version.

### Output

* `UrlFetcher`.
* `FetchedContent` contract usage.
* Tests using mocked HTTP responses.
* Tests for blocked hosts, redirects, content type, size limits, and timeout
  handling.
* No test should depend on a live external website.

---

## Phase 2.5 - HTML Extraction

### Scope

* Add `beautifulsoup4`.
* Add `trafilatura` only if it is used in this sub-phase.
* Receive HTML bytes from `UrlFetcher`.
* Parse the title, headings, paragraphs, lists, and tables.
* Prefer the main article or main content area.
* Preserve DOM document order.
* Build heading paths.
* Create `RawDocumentUnit` objects.
* Store HTML provenance.
* Collect warnings and extraction statistics.

### HTML Extraction Boundary

Extraction may:

* Remove `script`, `style`, and `noscript` elements.
* Select `main`, `article`, or a suitable content container.
* Remove navigation elements when the parser can identify them confidently.
* Decode HTML.
* Create units in DOM order.

Cleaning may not:

* Deduplicate paragraphs by semantic similarity.
* Remove boilerplate using strong domain-specific heuristics.
* Rewrite whitespace globally.
* Merge or split content by token count.
* Remove content based on domain-specific rules.
* Normalize sentences or punctuation.

BeautifulSoup is the primary structural unit builder. Trafilatura may support
main-content detection or fallback behavior, but it must not flatten the whole
page into a single plain-text block when that would lose heading, list, or
table structure.

### Typical Metadata

```text
extractor
block_type
block_index
html_tag
heading_level
list_type
source_url
final_url
```

### Notes

* `HtmlExtractor` must not send HTTP requests.
* Do not support dynamic JavaScript content.
* Do not implement the general cleaning pipeline here.
* More advanced content removal belongs to the future cleaning phase.

### Output

* `HtmlExtractor`.
* HTML fixtures.
* Tests for headings, paragraphs, lists, tables, malformed HTML, empty main
  content, deterministic `unit_index`, and deterministic `raw_unit_id`.

---

## Phase 2.6 - Extractor Registry and Extraction Service

### Scope

* Create an extractor registry.
* Select the correct extractor by source type or detected content format.
* Create an extraction application service.
* Convert runtime exceptions into structured source errors.
* Validate output identifiers through `ExtractionResult`.
* Aggregate extraction results, warnings, and statistics.

### Flow

```text
Source input
 -> load or fetch content
 -> build ExtractionInput
 -> select extractor
 -> extract
 -> validate ExtractionResult
 -> return RawDocumentUnit[]
```

### Notes

* The registry must not contain parsing logic.
* The service must not perform cleaning or chunking.
* Do not add a database repository in Phase 2.
* Do not add API routes unless explicitly requested.
* Duplicate `raw_unit_id` values must be rejected.
* Duplicate `unit_index` values must be rejected.
* Non-continuous `unit_index` values must be rejected.
* A source type mismatch must be rejected.

### Output

* `ExtractorRegistry`.
* Extraction application service.
* Integration tests for DOCX, PDF, and HTML.
* Consistent error mapping.

---

## Phase 2.7 - Final Verification and Documentation

### Scope

* Run all schema and extraction tests.
* Verify that all three extractors follow the same output contract.
* Verify deterministic ordering.
* Verify deterministic `raw_unit_id` generation.
* Verify that derived fields are generated by schemas.
* Verify unknown-field rejection.
* Verify warning and error behavior.
* Produce the final Phase 2 report.

### Acceptance Criteria

* DOCX, PDF, and HTML can produce `ExtractionResult`.
* Every unit preserves source and document lineage.
* Every unit has deterministic `unit_index`.
* Every unit has deterministic `raw_unit_id`.
* No blank units are returned.
* No duplicate `raw_unit_id` values exist.
* No duplicate `unit_index` values exist.
* Unit indexes are continuous from `0`.
* Document order is deterministic.
* PDF page numbers are valid.
* DOCX and HTML do not fabricate page numbers.
* Parser-specific values exist only in `extra_metadata`.
* Invalid input produces structured domain errors.
* Tests do not depend on external services.
* No cleaning, chunking, embedding, indexing, or persistence implementation is
  included.

---

## 9. Recommended Implementation Order

```text
2.1 Extraction core contracts
2.2 DOCX extractor
2.3 PDF extractor
2.4 URL fetcher
2.5 HTML extractor
2.6 Registry and extraction service
2.7 Final verification and documentation
```

Move to the next sub-phase only when:

* The current implementation is complete.
* Unit tests pass.
* Outputs comply with the Phase 1 schemas.
* No unrelated scope has been added.
* Existing contracts are not changed without a clear architectural reason.
