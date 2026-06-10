

# Phase 2.2: DOCX Extraction

Parent phase: `phase_2_source_extraction_overview.md`

Depends on: `phase_2_1_extraction_core_contracts.md`

## 1. Purpose

Implement the first real source extractor: `DocxExtractor`.

The extractor must convert valid DOCX bytes into an ordered
`ExtractionResult` containing `RawDocumentUnit` objects.

The target flow is:

```text
DOCX bytes
 -> ExtractionInput
 -> DocxExtractor
 -> ExtractionResult
      -> ordered RawDocumentUnit objects
      -> warnings
      -> extraction statistics
```

Phase 2.2 must use the contracts established in Phase 2.1 without redefining
them.

---

## 2. Scope

Implement:

* DOCX parsing from `ExtractionInput.content_bytes`.
* Paragraph extraction.
* Basic heading detection.
* Heading-path construction.
* Table extraction.
* Deterministic TSV table serialization.
* Paragraph and table ordering preservation.
* Deterministic `unit_index` and `raw_unit_id`.
* DOCX-specific metadata.
* DOCX extraction warnings and statistics.
* Runtime error behavior.
* Focused and regression tests.

---

## 3. Dependency

Add `python-docx` as a runtime dependency using the dependency style already
used in `backend/pyproject.toml`.

Do not add:

```text
PyMuPDF
beautifulsoup4
trafilatura
httpx runtime
OCR libraries
Microsoft Word automation libraries
LibreOffice integration
```

The dependency change must be limited to what is required by `DocxExtractor`.

---

## 4. Expected Files

Expected additions or updates:

```text
backend/pyproject.toml
backend/app/providers/extraction/docx_extractor.py
backend/tests/test_docx_extractor.py
```

Optional helper file, only if it improves readability:

```text
backend/app/providers/extraction/docx_blocks.py
```

Optional fixture directory:

```text
backend/tests/fixtures/docx/
```

Prefer generating simple DOCX fixtures in tests using `python-docx` when
practical. Do not commit unnecessary binary fixtures.

Do not create placeholder files for later PDF, HTML, URL, registry, or service
phases.

---

## 5. Public Contract

`DocxExtractor` must implement the Phase 2.1 `ContentExtractor` protocol.

Recommended structure:

```python
class DocxExtractor:
    source_type = SourceType.docx
    extractor_name = "python-docx"

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
* It must not perform cleaning or chunking.

The extractor version should be resolved from the installed package, for
example through `importlib.metadata.version("python-docx")`.

---

## 6. Input Validation

Before opening the document, validate:

```text
input_data.source_type == SourceType.docx
```

If the source type does not match, raise:

```text
ExtractionSourceTypeMismatchError
```

Do not rely only on:

* `original_filename`.
* File extension.
* `media_type`.

The DOCX package must still be opened and validated by `python-docx`.

Safe error details may include:

```text
source_id
document_id
original_filename
media_type
```

Error details must not include:

```text
content_bytes
raw document content
full unbounded parser output
```

---

## 7. Open DOCX From Bytes

Use an in-memory stream:

```python
from io import BytesIO

document = Document(BytesIO(input_data.content_bytes))
```

Do not write the input to local disk.

Known parser/package-opening failures must be converted to:

```text
ExtractionParsingError
```

Examples:

* Random bytes.
* Invalid ZIP package.
* Corrupted DOCX.
* Unsupported or unreadable Office package.

Do not catch every `Exception` and convert it into a parsing error.

Programming errors and unexpected implementation bugs should remain visible in
tests instead of being hidden behind a generic domain error.

---

## 8. Extraction Run Timestamp

Use `datetime` for the schema field, as required by the existing architecture.

Generate one timezone-aware UTC `datetime` when the extraction run begins:

```python
from datetime import datetime, timezone

run_extracted_at = datetime.now(timezone.utc)
```

Reuse the same value for every `RawDocumentUnit` created by that extraction
run.

Example:

```text
unit 0 extracted_at = 2026-06-10T03:20:15.123456+00:00
unit 1 extracted_at = 2026-06-10T03:20:15.123456+00:00
unit 2 extracted_at = 2026-06-10T03:20:15.123456+00:00
```

Do not call `datetime.now()` separately for every unit.

Do not use naive `datetime.utcnow()`.

Deterministic output requirements apply to content, order, indexes, IDs, heading
paths, and parser metadata. They do not require two extraction runs to have the
same `extracted_at`.

---

## 9. Preserve DOCX Body Order

Paragraphs and tables must be processed in the order in which they occur in the
DOCX body.

Do not use:

```python
for paragraph in document.paragraphs:
    ...

for table in document.tables:
    ...
```

That approach loses interleaving.

Example source order:

```text
Paragraph A
Table A
Paragraph B
Table B
```

Required output order:

```text
Paragraph A
Table A
Paragraph B
Table B
```

Implement an internal block iterator over body-level DOCX elements.

The iterator may yield:

```text
paragraph block
table block
unsupported block
```

The iterator must not expose `python-docx` objects through the public extraction
interface.

Known DOCX body elements that are not content blocks, such as the final section
properties element (`w:sectPr`), should be ignored rather than reported as
unsupported content. Emit unsupported-element warnings only for body-level items
that are reliably detected as unsupported user content.

`block_index` is assigned only after known structural-only elements are
excluded. Structural-only elements such as `w:sectPr` must not increment
`block_index`, `total_body_items`, `skipped_items`, or
`unsupported_item_count`.

Example:

```text
p      -> block_index 0
sectPr -> ignored entirely
tbl    -> block_index 1
```

If absolute raw XML child position is ever needed for audit/debugging, add a
separate metadata field such as `body_child_index` in a later task. Do not add it
in Phase 2.2.

---

## 10. Ordering Concepts

Keep these concepts separate:

### `block_index`

The zero-based position of a content-relevant body-level item observed by the
extractor after structural-only elements such as `w:sectPr` are excluded.

Store it in:

```python
extra_metadata["block_index"]
```

### `paragraph_index`

The zero-based position among paragraph blocks observed by the parser.

Store it in:

```python
extra_metadata["paragraph_index"]
```

### `table_index`

The zero-based position among table blocks observed by the parser.

Store it in:

```python
extra_metadata["table_index"]
```

### `unit_index`

The zero-based position among successfully emitted `RawDocumentUnit` objects.

It must be assigned as:

```python
unit_index = len(units)
```

A skipped blank or unsupported block increments parser-native counters but does
not consume a `unit_index`.

Example:

```text
block_index 0 -> heading emitted   -> unit_index 0
block_index 1 -> blank skipped     -> no unit_index
block_index 2 -> paragraph emitted -> unit_index 1
```

---

## 11. Paragraph Extraction

For each paragraph block:

```python
content = paragraph.text
```

Rules:

* Use `content.strip()` only to decide whether content is blank.
* Do not replace the output with the stripped value.
* Preserve the text returned by `python-docx`.
* Do not normalize whitespace in the extractor.
* Do not collapse repeated spaces.
* Do not rewrite punctuation.
* Do not merge paragraphs.
* Do not split paragraphs.
* A valid paragraph creates one `RawDocumentUnit`.
* A whitespace-only paragraph is skipped.
* A normal blank paragraph increments `skipped_items`.
* A normal blank paragraph does not require a warning.

Paragraph metadata should include:

```python
{
    "parser": "python-docx",
    "parser_version": extractor_version,
    "block_type": "paragraph",
    "block_index": block_index,
    "paragraph_index": paragraph_index,
    "style_name": style_name,
}
```

Do not store full paragraph content in `extra_metadata`.

`style_name` must be read defensively:

```python
style_name = getattr(getattr(paragraph, "style", None), "name", None)
```

Only run heading-style regex matching when `style_name` is a string. If
`style_name` is missing or blank, omit the `style_name` key from metadata rather
than storing `None`.

---

## 12. Heading Detection

Support basic built-in heading styles:

```text
Heading 1
Heading 2
Heading 3
...
```

Heading detection may use a strict style-name pattern such as:

```text
^Heading ([1-9][0-9]*)$
```

Do not attempt advanced heading inference in this phase.

Deferred heading behavior:

* Custom heading styles.
* Localized style names.
* XML outline-level inference.
* Font-size-based heading inference.
* Domain-specific heading rules.

If a paragraph is detected as a heading:

* Treat it as a valid emitted unit.
* Add `heading_level` to metadata.
* Update the active heading state.
* Include the heading itself in its resulting `heading_path`.
* Set `section` to the nearest current heading.

Use an active heading-state map keyed by heading level:

```python
heading_state: dict[int, str] = {}
```

When a heading is encountered:

1. Store the heading text at its level.
2. Remove all stored headings with a deeper level.
3. Build `heading_path` from known levels in ascending order.
4. Assign that path to the heading unit itself.

Do not create synthetic headings for missing levels.

Example:

```text
Heading 1: Human Resources
Heading 2: Leave Policy
Heading 3: Annual Leave
```

Active path:

```python
[
    "Human Resources",
    "Leave Policy",
    "Annual Leave",
]
```

If the next heading is:

```text
Heading 2: Salary Policy
```

The new path must be:

```python
[
    "Human Resources",
    "Salary Policy",
]
```

The previous level-3 heading must be removed.

---

## 13. Heading-Level Gaps

A heading level may skip a parent level:

```text
Heading 1
Heading 3
```

Do not create synthetic headings.

Build the path from the heading levels currently known.

The extractor should remain deterministic and must not invent missing content.

If the implementation records the gap as a warning, it must use a stable warning
code and must not fail extraction.

A warning for heading gaps is optional in Phase 2.2.

---

## 14. Heading Path for Normal Paragraphs and Tables

Normal paragraphs inherit the active heading path.

Tables also inherit the active heading path.

Example:

```text
Heading 1: Human Resources
Heading 2: Leave Policy
Paragraph: Employees receive annual leave.
Table: Leave type / Days
```

The paragraph and table should contain:

```python
heading_path=[
    "Human Resources",
    "Leave Policy",
]
section="Leave Policy"
```

Before any heading is encountered:

```python
heading_path=[]
section=None
```

Use isolated list values for every unit. Do not share one mutable heading list
across units.

---

## 15. Table Extraction

Each valid body-level table creates one `RawDocumentUnit`.

Use one deterministic serialization format:

```text
tsv_escaped_v1
```

Basic output format:

* One table row per line.
* One cell per tab-separated field.
* Preserve source row order.
* Preserve source cell order.

Example:

```text
Leave type	Days
Annual leave	12
Marriage leave	3
```

Metadata should include:

```python
{
    "parser": "python-docx",
    "parser_version": extractor_version,
    "block_type": "table",
    "block_index": block_index,
    "table_index": table_index,
    "row_count": row_count,
    "column_count": column_count,
    "serialization_format": "tsv_escaped_v1",
}
```

---

## 16. Table Cell Escaping

Use a stable escaping rule for cell text.

Recommended order:

```python
escaped = (
    cell_text
    .replace("\\", "\\\\")
    .replace("\r\n", "\n")
    .replace("\r", "\n")
    .replace("\t", "\\t")
    .replace("\n", "\\n")
)
```

Rules:

* Escape backslashes first.
* Normalize CRLF and CR to LF before escaping line breaks.
* Escape internal tabs as `\\t`.
* Escape internal line breaks as `\\n`.
* Do not strip meaningful cell text.
* Do not perform semantic cleaning.

The same table input must always produce the same serialized text.

---

## 17. Blank Table Behavior

A table whose serialized content is empty or whitespace-only must not create a
`RawDocumentUnit`.

Detect blank tables from raw cell text before serialization. A table is blank
when every observed cell has `cell_text.strip() == ""`. Do not rely only on the
serialized TSV string, because an all-empty table can serialize to separator-only
text.

Example separator-only serialized content:

```text
\t
\t
```

For a blank table:

* Increment `skipped_items`.
* Increment table/body counters as appropriate.
* A warning is optional unless the table is malformed or unsupported.

If all document blocks are skipped and no units remain, raise:

```text
ExtractionNoContentError
```

Do not return an empty successful `ExtractionResult`.

`row_count` and `column_count` are practical parser-observed counts, not layout
reconstruction. Use:

```python
row_count = len(table.rows)
row_column_counts = [len(row.cells) for row in table.rows]
column_count = max(row_column_counts, default=0)
```

DOCX merged cells and uneven rows may make this imperfect. Do not attempt to
resolve visual merged-cell semantics in Phase 2.2.

---

## 18. Complex DOCX Structures

The initial implementation does not need to reconstruct:

```text
merged cells
nested tables
images
charts
drawings
text boxes
embedded spreadsheets
complex list numbering
headers
footers
footnotes
endnotes
comments
tracked changes
section layout
page layout
```

Behavior:

* Preserve parser output when it is safely available.
* Skip unsupported body elements.
* Add a non-fatal warning when unsupported elements are explicitly detected.
* Do not introduce OCR.
* Do not attempt visual-layout reconstruction.

Nested tables may remain unsupported in the first implementation. Document the
actual behavior in the final report.

DOCX files are ZIP packages, but Phase 2.2 must not implement custom ZIP
inspection or security scanning. Resource limits and upload hardening belong to
the intake/upload layer or a dedicated security-hardening task. The extractor
must read bytes in memory, avoid temporary files, avoid execution, and rely on
`python-docx` and the underlying package validation for opening the document.

---

## 19. Page Information

DOCX is flow-based and `python-docx` does not provide reliable rendered page
numbers.

Every DOCX raw unit must use:

```python
page_start=None
page_end=None
```

Do not:

* Infer page number from page breaks.
* Infer page number from paragraph count.
* Infer page number from section breaks.
* Render DOCX to PDF.
* Use Microsoft Word or LibreOffice automation.
* Fabricate page numbers.

---

## 20. Document Content Type

Use the existing `DocumentContentType` values.

Before implementation, inspect the current enum.

Preferred mapping when supported:

```text
heading paragraph -> paragraph
normal paragraph  -> paragraph
table             -> table
```

The current `DocumentContentType` enum does not define `heading` or `text`.
Do not expand the enum in Phase 2.2. A DOCX heading is still a paragraph with a
heading style, so represent it as:

```python
content_type=DocumentContentType.paragraph
extra_metadata={
    "block_type": "heading",
    "heading_level": heading_level,
    "style_name": style_name,
}
```

Normal paragraphs should use:

```python
content_type=DocumentContentType.paragraph
extra_metadata={
    "block_type": "paragraph",
    "style_name": style_name,
}
```

This keeps the shared document schema stable while preserving DOCX-specific
structure in parser metadata.

Do not redefine `DocumentContentType` inside the DOCX extractor.

---

## 21. Raw Unit Creation

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
content
content_type
page_start=None
page_end=None
section
heading_path
extracted_at=run_extracted_at
extra_metadata
```

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

## 22. Warnings

Use `ExtractionWarning` only for non-fatal conditions.

Possible warning codes:

```text
unsupported_docx_element
unsupported_embedded_object
malformed_docx_table
heading_level_gap
```

Warning rules:

* Codes must be stable snake_case values.
* `stage` must be `parsing` or `extracting`.
* `item_index` refers to a parser-native block/item.
* `unit_index` is only provided when the warning relates to an emitted unit.
* Error details and warnings must not contain binary content.
* Normal blank paragraphs should not create warnings.
* Unsupported items may create warnings when reliably detected.

Do not create warnings for behavior the implementation cannot actually detect.

---

## 23. Extraction Statistics

Build:

```python
ExtractionStats(
    total_units=len(units),
    skipped_items=skipped_items,
    warning_count=len(warnings),
    extra_metadata={
        "total_body_items": total_body_items,
        "paragraph_count": paragraph_count,
        "heading_count": heading_count,
        "table_count": table_count,
        "unsupported_item_count": unsupported_item_count,
    },
)
```

Counter definitions must be documented in code or tests.

Recommended semantics:

* `total_body_items`: content-relevant body items observed by the extractor
  after structural-only elements such as `w:sectPr` are excluded.
* `paragraph_count`: paragraph blocks observed, including blank paragraphs.
* `heading_count`: non-blank paragraph blocks observed with built-in heading
  style and emitted as heading paragraph units.
* `table_count`: table blocks observed.
* `unsupported_item_count`: unsupported body-level items skipped.
* `skipped_items`: observed content candidates that did not emit units, such as
  blank paragraphs, blank tables, or reliably unsupported content items.

Keep observed and emitted counters separate:

```text
observed counters -> total_body_items, paragraph_count, heading_count,
                     table_count, unsupported_item_count, skipped_items
emitted counters  -> stats.total_units, unit_index, raw_unit_id
```

Example:

```text
p heading nonblank -> paragraph_count+1, heading_count+1, emitted unit_index 0
p blank            -> paragraph_count+1, skipped_items+1, no unit_index
tbl nonblank       -> table_count+1, emitted unit_index 1
sectPr             -> ignored entirely
```

Do not add DOCX-specific first-class fields to `ExtractionStats`.

---

## 24. ExtractionResult

Return:

```python
ExtractionResult(
    source_id=input_data.source_id,
    document_id=input_data.document_id,
    source_type=SourceType.docx,
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
Prefer statistics and counter-like metadata there. Keep `original_filename`,
`media_type`, and `charset` on `ExtractionInput`; future service/source metadata
work can decide where to persist file-level provenance. Parser/block-specific
provenance belongs in each unit's `extra_metadata`.

Do not duplicate full content or binary data in any metadata field.

---

## 25. Runtime Error Behavior

### Source type mismatch

Raise:

```text
ExtractionSourceTypeMismatchError
```

### Invalid or corrupt DOCX

Raise:

```text
ExtractionParsingError
```

### Valid DOCX package with no extractable units

Raise:

```text
ExtractionNoContentError
```

### Output invariant failure

If output construction violates an extraction contract, use:

```text
ExtractionInvariantError
```

only if that error exists in the Phase 2.1 taxonomy and wrapping is useful.

Do not unnecessarily hide a Pydantic validation or implementation bug.

Do not catch every exception broadly.

Do not return `None`.

Do not return an empty successful result.

---

## 26. Test Fixture Strategy

Prefer creating DOCX bytes in memory in tests:

```text
python-docx Document
 -> add paragraphs/headings/tables
 -> save to BytesIO
 -> use BytesIO.getvalue()
```

This makes fixtures:

* Easy to understand.
* Deterministic.
* Easy to customize per test.
* Independent of local filesystem paths.

Static fixture files may be used only when required to represent a document
structure that cannot be created clearly in test code.

Tests must not depend on Microsoft Word or LibreOffice.

---

## 27. Required Tests

### Basic paragraph extraction

Test:

* One normal paragraph.
* Multiple paragraphs.
* Paragraph order.
* Whitespace-only paragraph skipped.
* Content returned by the parser is preserved.
* `page_start` and `page_end` are `None`.
* Computed metrics and hash appear through the schema.
* Extractor does not pass computed fields manually.

### Ordering

Create:

```text
Paragraph A
Table A
Paragraph B
Table B
```

Assert output order:

```text
Paragraph A
Table A
Paragraph B
Table B
```

Assert:

```text
unit_index = 0, 1, 2, 3
```

Assert corresponding deterministic IDs.

### Heading behavior

Test:

* Heading 1.
* Heading 1 followed by Heading 2.
* Heading 1 -> Heading 2 -> Heading 3.
* Heading 3 followed by Heading 2 resets lower levels.
* Normal paragraph inherits heading path.
* Table inherits heading path.
* Heading unit includes itself in the heading path.
* Content before the first heading has empty path and no section.
* Heading-level gaps do not create invented headings.

### Table behavior

Test:

* Single-row table.
* Multi-row table.
* Row and cell order.
* Stable TSV serialization.
* Internal tab escaping.
* Internal newline escaping.
* Backslash escaping.
* Blank-table behavior based on raw cell text, not separator-only serialized
  output.
* Table metadata counts and format.
* `column_count` equals the maximum observed `len(row.cells)` across rows.

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
table serialization
```

Do not compare `extracted_at` across separate runs.

Within one run, assert that every unit has the same `extracted_at`.

### Statistics

Test:

* `total_units`.
* `skipped_items`.
* `warning_count`.
* `total_body_items`.
* `paragraph_count`.
* `heading_count`.
* `table_count`.
* `unsupported_item_count` when supported.
* Known structural-only elements such as `w:sectPr` do not affect
  `total_body_items`, `skipped_items`, `unsupported_item_count`, or
  `block_index`.

### Errors

Test:

* Source type mismatch.
* Random invalid bytes.
* Corrupted DOCX package.
* Empty DOCX.
* DOCX containing only blank paragraphs.
* Safe error details contain no input bytes.

### Protocol

The current `ContentExtractor` protocol is used for static structural typing and
is not runtime-checkable. Do not require `isinstance(extractor,
ContentExtractor)` in Phase 2.2 tests unless the protocol is explicitly updated
with `@runtime_checkable` as part of this phase.

Because this project currently does not run mypy or pyright, pytest does not
prove protocol conformance from type annotations alone. Do not add tests whose
only assertion is that a typed helper accepts `DocxExtractor`.

Preferred Phase 2.2 test strategy:

* Test `DocxExtractor.extract(input_data)` behavior directly.
* Optionally use a typed helper for readability, but do not claim it proves
  runtime protocol conformance.
* Keep protocol conformance covered by method shape, behavior tests, and the
  Phase 2.1 shared contract.

Optional helper:

```python
def run_extractor(extractor: ContentExtractor, input_data: ExtractionInput):
    return extractor.extract(input_data)
```

If this helper is used, still assert real extraction behavior and a valid
`ExtractionResult`.

---

## 28. Verification Commands

Focused verification:

```bash
cd backend
pytest tests/test_docx_extractor.py
```

Run related extraction tests:

```bash
pytest \
  tests/test_document_schema.py \
  tests/test_extraction_schema.py \
  tests/test_extraction_interface.py \
  tests/test_extraction_errors.py \
  tests/test_extraction_ids.py \
  tests/test_docx_extractor.py
```

Final regression:

```bash
pytest
```

If the repository already provides linting or type-check commands, run those
commands without adding new tooling.

---

## 29. Explicitly Out Of Scope

Do not implement:

```text
PDF extraction
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
chunking
tokenization
embedding
indexing
retrieval
reranking
answer generation
OCR
image extraction
chart extraction
text-box extraction
page-number calculation
JavaScript rendering
website crawling
```

Do not modify unrelated modules.

Do not expand schemas unless an actual contract conflict is found and reported.

---

## 30. Acceptance Criteria

Phase 2.2 is complete only when:

1. `DocxExtractor` reads DOCX bytes through `ExtractionInput` and returns a
   valid `ExtractionResult`.
2. Paragraph and table body order is preserved.
3. Built-in DOCX headings produce deterministic `heading_path` and `section`
   values.
4. Tables use deterministic `tsv_escaped_v1` serialization.
5. Every emitted unit has continuous `unit_index` and deterministic
   `raw_unit_id`.
6. DOCX parser metadata, warnings, and observed/emitted statistics follow this
   plan and the Phase 2.1 contracts.
7. Source type mismatch, invalid/corrupt DOCX input, and no-content documents
   raise the expected extraction errors.
8. Phase 2.2 scope stays limited to DOCX extraction; no service, registry, API,
   persistence, cleaning, chunking, indexing, retrieval, or other source
   extractors are added.
9. Focused DOCX tests, related extraction tests, and full backend regression
   pass.

---

## 31. Expected Output

After Phase 2.2, the system must support:

```text
Valid DOCX bytes
 -> DocxExtractor
 -> ExtractionResult
      -> ordered paragraph units
      -> ordered heading units
      -> ordered table units
      -> deterministic IDs and indexes
      -> heading lineage
      -> DOCX parser metadata
      -> warnings
      -> extraction statistics
```

---

## 32. Implementation Rule

Implement only Phase 2.2.

Before implementation:

1. Read the Phase 2 overview.
2. Read the completed Phase 2.1 specification and implementation.
3. Inspect the actual extraction schemas and runtime error classes.
4. Inspect the current `DocumentContentType`.
5. Inspect the current provider directory and import conventions.
6. Confirm the existing `ContentExtractor` protocol signature.
7. Confirm the actual test-file naming used by Phase 2.1.

After implementation, report:

* Dependency added.
* Files created.
* Files modified.
* DOCX block-order strategy.
* Heading-detection strategy.
* Table-serialization rules.
* Warning behavior.
* Error behavior.
* Known DOCX limitations.
* Focused test result.
* Full regression result.
* Any schema or contract conflict encountered.
