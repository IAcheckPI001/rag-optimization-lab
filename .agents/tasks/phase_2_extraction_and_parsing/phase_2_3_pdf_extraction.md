# Phase 2.3: PDF Extraction

Parent phase: `phase_2_source_extraction_overview.md`

Depends on:

* `phase_2_1_extraction_core_contracts.md`
* `phase_2_2_docx_extraction.md`

## 1. Purpose

Implement `PdfExtractor`, the second real source extractor in Phase 2.

The extractor must convert valid PDF bytes into an ordered `ExtractionResult`
containing `RawDocumentUnit` objects.

The target flow is:

```text
PDF bytes
 -> ExtractionInput
 -> PdfExtractor
 -> ExtractionResult
      -> ordered text-block RawDocumentUnit objects
      -> warnings
      -> extraction statistics
```

Phase 2.3 must use the contracts established in Phase 2.1 without redefining
them. It must also follow the boundary discipline used by Phase 2.2: parser
logic stays inside the extraction provider, parser-specific provenance stays in
unit `extra_metadata`, and observed counters stay in `ExtractionStats`.

---

## 2. Scope

Implement:

* PDF parsing from `ExtractionInput.content_bytes`.
* Page iteration in source order.
* Text block extraction in a deterministic, reasonable reading order.
* One `RawDocumentUnit` per emitted non-blank text block.
* One-based PDF page ranges.
* PDF-specific parser metadata.
* Deterministic `unit_index` and `raw_unit_id`.
* PDF extraction warnings and statistics.
* Runtime error behavior.
* Focused and regression tests.

---

## 3. Dependency

Add `PyMuPDF` as a runtime dependency using the dependency style already used in
`backend/pyproject.toml`.

Before implementation, inspect the installed PyMuPDF package and use one
currently supported import convention consistently. Do not mix `fitz` and
`pymupdf` imports in the extractor or tests.

Do not add:

```text
OCR libraries
PDF table extraction libraries
PDF rendering services
LibreOffice integration
Playwright
beautifulsoup4
trafilatura
httpx runtime
```

The dependency change must be limited to what is required by `PdfExtractor`.

---

## 4. Expected Files

Expected additions or updates:

```text
backend/pyproject.toml
backend/app/providers/extraction/pdf_extractor.py
backend/tests/test_pdf_extractor.py
```

Optional helper file, only if it improves readability:

```text
backend/app/providers/extraction/pdf_blocks.py
```

Prefer generating simple PDF fixtures in tests using PyMuPDF when practical. Do
not commit unnecessary binary fixtures.

Do not create placeholder files for later HTML, URL, registry, service, API, or
database phases.

---

## 5. Public Contract

`PdfExtractor` must implement the Phase 2.1 `ContentExtractor` protocol.

Recommended structure:

```python
class PdfExtractor:
    source_type = SourceType.pdf
    extractor_name = "pymupdf"

    def extract(
        self,
        input_data: ExtractionInput,
    ) -> ExtractionResult:
        ...
```

Rules:

* The extractor is synchronous.
* It receives `ExtractionInput`.
* It returns `ExtractionResult`.
* It must not receive a filesystem path.
* It must not receive a FastAPI upload object.
* It must not write temporary files.
* It must not persist data.
* It must not perform cleaning, chunking, OCR, rendering, or table
  reconstruction.

The extractor version must be resolved from the installed PyMuPDF package
metadata. If package metadata is unexpectedly unavailable, raise an
`ExtractionInvariantError` or another explicit configuration failure. Do not
silently use `"unknown"` for Phase 2.3, because that weakens extraction
reproducibility.

---

## 6. Input Validation

Before opening the PDF, validate:

```text
input_data.source_type == SourceType.pdf
```

If the source type does not match, raise:

```text
ExtractionSourceTypeMismatchError
```

Do not rely only on:

* `original_filename`.
* File extension.
* `media_type`.

The PDF package must still be opened and validated by PyMuPDF.

Safe error details may include:

```text
source_id
document_id
source_type
original_filename
media_type
```

Error details must not include:

```text
content_bytes
raw document content
full extracted text
full unbounded parser output
```

---

## 7. Open PDF From Bytes

Open the PDF from memory using the selected PyMuPDF import convention.

Example shape:

```python
document = pymupdf.open(stream=input_data.content_bytes, filetype="pdf")
try:
    ...
finally:
    document.close()
```

If the installed package supports a stable context manager for the chosen import
API, a context manager may be used instead. The lifecycle requirement is the
same: the document must be closed on success, parsing failures, encrypted PDF
failures, no-content failures, and output invariant failures.

Known parser-opening failures must be converted to:

```text
ExtractionParsingError
```

Examples:

* Random bytes.
* Corrupted PDF.
* Unsupported PDF structure that PyMuPDF cannot open.
* Encrypted PDF that cannot be read without a password.

Do not catch every `Exception` and convert it into a parsing error. Programming
errors and unexpected implementation bugs should remain visible in tests.

---

## 8. Encrypted Or Password-Protected PDFs

An encrypted PDF may open successfully before text access is possible.

After opening, inspect the document encryption/authentication state using the
installed PyMuPDF API.

Rules:

* Do not try to crack passwords.
* Do not add password support to `ExtractionInput` in Phase 2.3.
* Do not log passwords, content bytes, or extracted text.
* Close the document before raising an error.
* Raise `ExtractionParsingError` when the PDF requires authentication or cannot
  be read with the available empty/no-password state.

---

## 9. Extraction Run Timestamp

Use `datetime` for the schema field, as required by the existing architecture.

Generate one timezone-aware UTC `datetime` when the extraction run begins:

```python
from datetime import datetime, timezone

run_extracted_at = datetime.now(timezone.utc)
```

Reuse the same value for every `RawDocumentUnit` created by that extraction
run.

Do not call `datetime.now()` separately for every unit.

Do not use naive `datetime.utcnow()`.

Deterministic output requirements apply to content, order, indexes, IDs, page
ranges, and parser metadata. They do not require two extraction runs to have the
same `extracted_at`.

---

## 10. PDF Unit Granularity

Phase 2.3 emits one `RawDocumentUnit` per non-blank PDF text block.

Do not emit one unit per whole page in Phase 2.3. Text-block units provide more
useful provenance for later cleaning, chunking, retrieval, and citation while
remaining practical with PyMuPDF.

Rules:

* Iterate pages in source order.
* Extract text blocks from each page in a deterministic, reasonable reading
  order using PyMuPDF's supported sorted block extraction option when
  available.
* Emit only non-blank text blocks.
* Use `content.strip()` only for blank detection.
* Preserve the parser-produced block text in `content`.
* Do not normalize whitespace.
* Do not collapse repeated spaces.
* Do not rewrite punctuation.
* Do not merge blocks.
* Do not split blocks.
* Do not remove headers or footers.
* Do not infer headings or sections from font size, coordinates, or text shape.

PDF reading order may be imperfect. Phase 2.3 should prefer deterministic,
reasonable parser order over complex layout reconstruction.

---

## 11. Ordering Concepts

Keep these concepts separate:

### `page_index`

The zero-based page position in the PDF.

Store it in:

```python
extra_metadata["page_index"]
```

### `page_number`

The one-based page number used for user-facing provenance and citation.

Store it in:

```python
page_start=page_number
page_end=page_number
extra_metadata["page_number"]
```

### `page_block_index`

The zero-based block position inside the page after the selected PyMuPDF
ordering strategy is applied.

Store it in:

```python
extra_metadata["page_block_index"]
```

Use `page_block_index` instead of `block_index` for PDF metadata. DOCX
`block_index` is a document-level body item position, while PDF block positions
are page-local. The different name prevents cross-source confusion.

### `document_block_index`

Optional metadata only.

If implemented, it means the zero-based observed block position across all
pages, including text, blank text, and non-text blocks returned by PyMuPDF.

Do not make `document_block_index` required. Do not use it instead of
`unit_index`.

### `unit_index`

The zero-based position among successfully emitted `RawDocumentUnit` objects.

It must be assigned as:

```python
unit_index = len(units)
```

A skipped blank text block or unsupported non-text block increments
parser-native counters but does not consume a `unit_index`.

---

## 12. Text Block Extraction

For each text block:

```text
content = parser-provided block text
```

Rules:

* A valid non-blank text block creates one `RawDocumentUnit`.
* A whitespace-only text block is skipped.
* A blank text block increments `blank_text_block_count`.
* A blank text block increments `skipped_items`.
* A normal blank text block does not require a warning.
* A page with no emitted non-blank text units increments `blank_page_count`.

Text-block metadata should include:

```python
{
    "parser": "pymupdf",
    "parser_version": extractor_version,
    "block_type": "text",
    "page_index": page_index,
    "page_number": page_number,
    "page_block_index": page_block_index,
    "bbox": bbox,
}
```

Optional metadata:

```text
document_block_index
pymupdf_block_number
pymupdf_block_type
page_rotation
```

`page_rotation` is optional. Tests must not require it unless the fixture
explicitly creates a rotated page and the implementation intentionally records
the value.

Do not store full content separately in `extra_metadata`.

---

## 13. Bounding Boxes

Store the parser-provided bounding box in unit metadata when it is valid.

Do not round coordinates in Phase 2.3.

A valid bbox must contain four numeric values:

```text
x0
y0
x1
y1
```

Recommended MVP behavior for malformed parser blocks:

* If block text is extractable but bbox is malformed, skip the block.
* Add an `ExtractionWarning` with `warning_code="malformed_pdf_block"`.
* Use `stage=ProcessingStage.extracting`.
* Increment `skipped_items`.
* Do not raise `ExtractionInvariantError` unless the extractor itself produces
  an invalid output contract.

Warning details may include:

```text
parser
parser_version
page_index
page_number
page_block_index
pymupdf_block_type
```

Warning details must not include full text content or binary bytes.

This case is expected to be rare; keep validation small and practical.

---

## 14. Page Information

PDF has reliable page positions through PyMuPDF.

For every emitted unit:

```python
page_number = page_index + 1
page_start = page_number
page_end = page_number
```

Rules:

* Page numbers must start at `1`.
* `page_end` must equal `page_start` for text-block units.
* Do not fabricate headings or sections.
* Use `section=None`.
* Use `heading_path=[]`.

---

## 15. Document Content Type

Use the existing `DocumentContentType` values.

The current enum does not define `text` or `block`. Represent emitted PDF text
blocks as:

```python
content_type=DocumentContentType.paragraph
extra_metadata={
    "block_type": "text",
    ...
}
```

Do not expand `DocumentContentType` in Phase 2.3.

---

## 16. Raw Unit Creation

For every emitted unit:

```python
unit_index = len(units)

raw_unit_id = build_raw_unit_id(
    input_data.document_id,
    unit_index,
)
```

Create the `RawDocumentUnit` with:

```text
raw_unit_id
unit_index
source_id
document_id
source_type
source_uri
content
content_type
page_start
page_end
section=None
heading_path=[]
extracted_at=run_extracted_at
extra_metadata
```

The extractor must copy:

```python
source_uri=input_data.source_uri
```

even though the schema allows `source_uri=None`. This preserves lineage for
future PDF sources loaded from URLs, object storage, or other stable source
locations.

Do not provide:

```text
character_count
word_count
content_hash
```

Those fields remain computed by the schema.

The Phase 2.1 `ExtractionResult` validator is responsible for enforcing final
ordering, uniqueness, lineage, and statistics.

---

## 17. Warnings

Use `ExtractionWarning` only for non-fatal conditions.

Possible warning codes:

```text
unsupported_pdf_block
malformed_pdf_block
```

Warning rules:

* Codes must be stable snake_case values.
* `stage` must be `parsing` or `extracting`.
* `item_index` may refer to `document_block_index` when that value is available.
* `unit_index` is only provided when the warning relates to an emitted unit.
* Error details and warnings must not contain binary content.
* Normal blank text blocks should not create warnings.
* Unsupported non-text blocks may create warnings only when PyMuPDF exposes them
  reliably.
* Do not create warnings for behavior the implementation cannot actually
  detect.

---

## 18. Extraction Statistics

Build:

```python
ExtractionStats(
    total_units=len(units),
    skipped_items=skipped_items,
    warning_count=len(warnings),
    extra_metadata={
        "page_count": page_count,
        "blank_page_count": blank_page_count,
        "pages_with_text_count": pages_with_text_count,
        "total_observed_blocks": total_observed_blocks,
        "text_block_count": text_block_count,
        "blank_text_block_count": blank_text_block_count,
        "non_text_block_count": non_text_block_count,
    },
)
```

Counter definitions:

* `page_count`: total pages in the opened PDF.
* `blank_page_count`: pages that emitted no non-blank text units.
* `pages_with_text_count`: pages that emitted at least one non-blank text unit.
* `total_observed_blocks`: every block returned by PyMuPDF.
* `text_block_count`: observed text blocks, including blank text blocks.
* `blank_text_block_count`: text blocks skipped because `content.strip()` is
  empty.
* `non_text_block_count`: image or other non-text blocks observed when PyMuPDF
  exposes them.
* `skipped_items`: blank text blocks plus reliably observed unsupported or
  malformed blocks that did not emit units.

Counter relationship:

```text
pages_with_text_count + blank_page_count == page_count
blank_text_block_count <= text_block_count
stats.total_units == len(units)
stats.warning_count == len(warnings)
```

`skipped_items` is block-oriented. A page with no blocks increases
`blank_page_count`, but does not increase `skipped_items`.

Keep observed and emitted counters separate:

```text
observed counters -> page_count, blank_page_count, total_observed_blocks,
                     text_block_count, blank_text_block_count,
                     non_text_block_count, skipped_items
emitted counters  -> stats.total_units, unit_index, raw_unit_id
```

Do not add PDF-specific first-class fields to `ExtractionStats`.

---

## 19. Empty, Blank, And Image-Only PDFs

These cases must be distinguished internally but share the same public no-content
outcome when no units are emitted:

```text
PDF opens with 0 pages
PDF has pages but no blocks
PDF has only blank text blocks
PDF has only image/non-text blocks
```

If PyMuPDF opens the document successfully and no non-blank text units are
emitted, raise:

```text
ExtractionNoContentError
```

Do not treat a valid zero-page PDF as a parsing error merely because it has no
pages.

Successful partial extraction remains valid. For example, a PDF with some blank
pages and some text pages should return `ExtractionResult` and record the blank
pages through `blank_page_count`.

---

## 20. ExtractionResult

Return:

```python
ExtractionResult(
    source_id=input_data.source_id,
    document_id=input_data.document_id,
    source_type=SourceType.pdf,
    extractor_name=self.extractor_name,
    extractor_version=extractor_version,
    units=units,
    warnings=warnings,
    stats=stats,
)
```

Do not pass `extra_metadata` to `ExtractionResult`. The implemented Phase 2.1
schema does not include result-level metadata.

Do not use `ExtractionStats.extra_metadata` as a general provenance bucket.
Prefer statistics and counter-like metadata there. Parser/block-specific
provenance belongs in each unit's `extra_metadata`.

Do not duplicate full content or binary data in any metadata field.

---

## 21. Runtime Error Behavior

### Source type mismatch

Raise:

```text
ExtractionSourceTypeMismatchError
```

### Invalid, corrupt, or unreadable PDF

Raise:

```text
ExtractionParsingError
```

### Password-protected PDF requiring authentication

Raise:

```text
ExtractionParsingError
```

### Valid PDF with no extractable text units

Raise:

```text
ExtractionNoContentError
```

### Output invariant failure

If output construction violates an extraction contract, use:

```text
ExtractionInvariantError
```

only if wrapping is useful.

Do not unnecessarily hide a Pydantic validation or implementation bug.

If wrapping a `pydantic.ValidationError` from final `ExtractionResult`
construction:

* Catch it only around the final output construction.
* Preserve the original cause with `from exc`.
* Include only safe details such as `source_id`, `document_id`, `unit_count`,
  and `warning_count`.
* Do not catch all validation errors broadly around the whole extraction flow.

Do not catch every exception broadly.

Do not return `None`.

Do not return an empty successful result.

---

## 22. Test Fixture Strategy

Prefer creating PDF bytes in memory in tests using PyMuPDF:

```text
PyMuPDF document
 -> add pages
 -> insert text or images as needed
 -> save to bytes
 -> feed bytes through ExtractionInput
```

This makes fixtures:

* Easy to understand.
* Deterministic.
* Easy to customize per test.
* Independent of local filesystem paths.

Static fixture files may be used only when required to represent a PDF structure
that cannot be created clearly in test code.

Tests must not depend on external services, OCR engines, browsers, system PDF
viewers, or network access.

---

## 23. Required Tests

### Dependency and import

Test:

* PyMuPDF import smoke test using the chosen import convention.
* Extractor version resolves successfully and is not `"unknown"`.

### Basic PDF extraction

Test:

* One page with one text block.
* Multiple pages.
* Multiple text blocks on one page.
* Text block order is deterministic for simple-layout fixtures.
* Content returned by the parser is preserved.
* `page_start` and `page_end` are one-based and equal for each block unit.
* `source_uri` from `ExtractionInput` is copied to every emitted unit.
* Computed metrics and hash appear through the schema.
* Extractor does not pass computed fields manually.

### Ordering and IDs

Assert:

```text
unit_index = 0, 1, 2, ...
raw_unit_id = raw:{document_id}:{unit_index:06d}
```

Assert that `page_index`, `page_number`, and `page_block_index` describe parser
positions while `unit_index` describes emitted output order.

### Metadata

Test:

* Required metadata exists: `parser`, `parser_version`, `block_type`,
  `page_index`, `page_number`, `page_block_index`, `bbox`.
* `bbox` contains four numeric values.
* Optional metadata such as `document_block_index` and `page_rotation` is not
  required unless intentionally implemented.
* Metadata contains no binary content and does not duplicate full extracted
  content.

### Statistics

Test:

* `total_units`.
* `skipped_items`.
* `warning_count`.
* `page_count`.
* `blank_page_count`.
* `pages_with_text_count`.
* `total_observed_blocks`.
* `text_block_count`.
* `blank_text_block_count`.
* `non_text_block_count` when supported by the fixture.
* Counter relationships:
  `pages_with_text_count + blank_page_count == page_count` and
  `stats.total_units == len(units)`.

### Blank and no-content behavior

Test:

* PDF with some blank pages and some text pages succeeds.
* PDF with 0 pages, if PyMuPDF can create/open one, raises
  `ExtractionNoContentError`.
* PDF with pages but no blocks raises `ExtractionNoContentError`.
* PDF with only blank text blocks raises `ExtractionNoContentError` when
  practical to construct.
* Image-only PDF raises `ExtractionNoContentError` when practical to construct.

### Errors

Test:

* Source type mismatch.
* Random invalid bytes.
* Corrupted PDF.
* Password-protected PDF requiring authentication.
* Safe error details contain no input bytes and no extracted text.

### Determinism

Run the same input twice and compare:

```text
content
content_type
unit_index
raw_unit_id
page range
section
heading_path
parser metadata
```

Do not compare `extracted_at` across separate runs.

Within one run, assert that every unit has the same `extracted_at`.

### Protocol

The current `ContentExtractor` protocol is used for static structural typing and
is not runtime-checkable. Do not require `isinstance(extractor,
ContentExtractor)` in Phase 2.3 tests unless the protocol is explicitly updated
with `@runtime_checkable`.

Because this project currently does not run mypy or pyright, pytest does not
prove protocol conformance from type annotations alone. Test
`PdfExtractor.extract(input_data)` behavior directly.

---

## 24. Verification Commands

Focused verification:

```bash
cd backend
pytest tests/test_pdf_extractor.py
```

Run related extraction tests:

```bash
pytest \
  tests/test_document_schema.py \
  tests/test_extraction_schema.py \
  tests/test_extraction_interface.py \
  tests/test_extraction_errors.py \
  tests/test_extraction_ids.py \
  tests/test_docx_extractor.py \
  tests/test_pdf_extractor.py
```

Final regression:

```bash
pytest
```

If the repository already provides linting or type-check commands, run those
commands without adding new tooling.

---

## 25. Explicitly Out Of Scope

Do not implement:

```text
DOCX changes
HTML extraction
URL fetching
SSRF protection
ExtractorRegistry
ExtractionService orchestration
SourceError mapping
API routes
database repositories
database migrations
background jobs
object storage
content cleaning
paragraph deduplication
header or footer removal
heading inference
section inference
PDF table reconstruction
PDF column-layout reconstruction
PDF form extraction
PDF annotation extraction
PDF image extraction
OCR
scanned-document text recognition
chunking
tokenization
embedding
indexing
retrieval
reranking
answer generation
JavaScript rendering
website crawling
```

Do not modify unrelated modules.

Do not expand schemas unless an actual contract conflict is found and reported.

---

## 26. Acceptance Criteria

Phase 2.3 is complete only when:

1. `PdfExtractor` reads PDF bytes through `ExtractionInput` and returns a valid
   `ExtractionResult`.
2. Emitted units are non-blank PDF text blocks in deterministic page/block
   order.
3. Every emitted unit preserves `source_id`, `document_id`, `source_type`, and
   `source_uri` lineage.
4. Every emitted unit has one-based `page_start` and `page_end` values.
5. Every emitted unit has continuous `unit_index` and deterministic
   `raw_unit_id`.
6. PDF parser metadata, warnings, and observed/emitted statistics follow this
   plan and the Phase 2.1 contracts.
7. Blank pages are represented through `blank_page_count`; they do not emit
   blank units.
8. Source type mismatch, invalid/corrupt PDF input, password-protected PDF input,
   and no-content PDFs raise the expected extraction errors.
9. Phase 2.3 scope stays limited to PDF extraction; no service, registry, API,
   persistence, cleaning, chunking, indexing, retrieval, or other source
   extractors are added.
10. Focused PDF tests, related extraction tests, and full backend regression
    pass.

---

## 27. Expected Output

After Phase 2.3, the system must support:

```text
Valid PDF bytes
 -> PdfExtractor
 -> ExtractionResult
      -> ordered PDF text-block units
      -> deterministic IDs and indexes
      -> source lineage
      -> one-based page ranges
      -> PDF parser metadata
      -> warnings
      -> extraction statistics
```

---

## 28. Implementation Rule

Implement only Phase 2.3.

Before implementation:

1. Read the Phase 2 overview.
2. Read the completed Phase 2.1 specification and implementation.
3. Read the completed Phase 2.2 DOCX plan and implementation.
4. Inspect the actual extraction schemas and runtime error classes.
5. Inspect the current `DocumentContentType`.
6. Inspect the current provider directory and import conventions.
7. Inspect the installed PyMuPDF import convention and exception behavior.
8. Confirm the existing `ContentExtractor` protocol signature.
9. Confirm the actual test-file naming used by Phase 2.1 and Phase 2.2.

After implementation, report:

* Dependency added.
* Files created.
* Files modified.
* PyMuPDF import convention used.
* PDF block-order strategy.
* Page and block metadata strategy.
* Counter semantics.
* Warning behavior.
* Error behavior.
* Known PDF limitations.
* Focused test result.
* Full regression result.
* Any schema or contract conflict encountered.
