# Phase 3.2 - Deterministic Text Normalization

Status: Completed.

Depends on:

* Phase 3.1 cleaning contracts.
* Updated `CleanDocumentUnit`.
* `CleaningInput`, `CleaningResult`, warnings, dropped units, and stats schemas.
* Cleaning error taxonomy.
* `ContentCleaner` protocol.

## Completion Notes

* Added pure deterministic normalization helpers in
  `backend/app/rag/cleaning/normalization.py`.
* Added `tsv_escaped_v1` table parse/serialize helpers in
  `backend/app/rag/cleaning/table_text.py`.
* Implemented content-type dispatch for paragraph, list, table, code, and
  unknown content.
* Recorded only transformations that changed output content.
* Implemented stage-aware control cleanup:
  line endings -> content-type whitespace policy -> residual unsafe control
  cleanup.
* Preserved table row/column delimiters and escaped cell semantics.
* Preserved code indentation, tabs, repeated spaces, and outer blank lines.
* Kept unknown content conservative by preserving tabs and NBSP.
* Implemented internal normalization warnings for replacement characters and
  removed unsafe controls.
* Deferred `possible_mojibake`, blank-unit dropping, clean-unit construction,
  public `CleaningWarning` assembly, filtering, and deduplication to later
  phases.
* Added focused normalization tests in
  `backend/tests/test_cleaning_normalization.py`.
* Verification completed with full backend regression:
  `374 passed, 2 warnings`.

## Purpose

Implement deterministic, pure text normalization helpers for DOCX, PDF, and HTML
raw units without constructing full clean results and without source-aware noise
filtering or deduplication.

This phase answers:

```text
Given one raw unit content and content type, what normalized content and rule
codes should be produced?
```

It does not answer:

```text
Should this unit be dropped as source-specific noise?
How are clean IDs and clean indexes assigned?
How are stats and dropped-unit records assembled?
```

Those belong to later sub-phases.

## Current Implementation Facts

Phase 2 extractors already perform some parser-local normalization:

* DOCX tables serialize as `tsv_escaped_v1`.
* HTML structural text normalizes line endings, NBSP, and horizontal whitespace.
* HTML code blocks preserve preformatted text more carefully.
* PDF text blocks are parser-produced text and may contain layout artifacts.

Phase 3.2 should still be idempotent and deterministic over these outputs. It
must not assume Phase 2 has already fully cleaned content.

Headings are not represented by `DocumentContentType.heading`; they are
represented as:

```text
content_type = paragraph
extra_metadata.block_type = heading
```

Tables are represented by:

```text
content_type = table
extra_metadata.serialization_format = tsv_escaped_v1
```

Code is represented by:

```text
content_type = code
```

HTML list items are represented by:

```text
content_type = list
extra_metadata.block_type = list_item
```

## Proposed Module Layout

Add internal pure helper modules under:

```text
backend/app/rag/cleaning/normalization.py
backend/app/rag/cleaning/table_text.py
```

Keep these modules independent of:

* PyMuPDF
* python-docx
* BeautifulSoup
* HTTPX
* FastAPI
* repositories
* external services

No new dependency is needed.

## Core Data Shape

Use a small internal dataclass or Pydantic-free value object for helper return
values. Example:

```python
@dataclass(frozen=True)
class NormalizedContent:
    content: str
    transformations: tuple[str, ...]
    warnings: tuple[NormalizationWarning, ...] = ()
```

This does not need to be a shared public schema unless Phase 3.3 needs it.

## Rule Code Policy

`transformations` must contain stable machine-readable rule codes.

Recommended rule codes:

```text
unicode_nfc
line_endings_normalized
control_characters_removed
nbsp_normalized
prose_whitespace_normalized
list_whitespace_normalized
table_cells_normalized
code_outer_blank_lines_trimmed
```

Open point before implementation:

* Decide whether `transformations` records rules attempted or only rules that
  changed content.

Recommended decision:

* Record only rules that changed output content.
* This keeps `modified_unit_count` aligned with `content != raw.content`.
* If the team wants attempted rules for observability, use stats counters, not
  per-unit `transformations`.

## Unicode Normalization

Implement:

```text
NFC normalization
```

Do not implement:

* NFKC by default
* heuristic mojibake repair
* spelling correction
* punctuation rewriting
* lowercasing
* translation

Warnings may be emitted for:

```text
replacement_character_detected
possible_mojibake
```

Warnings must not rewrite text unless a reliable deterministic rule exists.

## Line Ending Normalization

Normalize:

```text
CRLF -> LF
CR   -> LF
```

All normalized output uses `\n`.

## Control Character Policy

Control cleanup must be stage-aware. Do not apply one global rule before the
content-type whitespace policy has had a chance to interpret tabs and other
horizontal whitespace.

Pipeline order:

```text
line-ending normalization
-> content-type whitespace normalization
-> unsafe residual control-character cleanup
```

Rules:

* Prose and list content should convert tabs and horizontal whitespace to
  ordinary spaces during their whitespace normalization step.
* Table content must preserve real tab delimiters and escaped cell tab
  semantics.
* Code content must preserve tabs, repeated spaces, and indentation.
* Unknown content should preserve tabs conservatively.
* After content-type whitespace normalization, remove unsafe residual C0
  controls and DEL.
* Always preserve `\n`.
* Preserve `\t` only where the content-type policy requires it: table, code,
  and unknown fallback.

Be conservative with Unicode format characters. Do not remove all `Cf`
characters by default without a separate reviewed policy.

If characters are removed, attach rule code:

```text
control_characters_removed
```

Optional warning:

```text
suspicious_control_characters_removed
```

## Prose Normalization

Applies to:

* `DocumentContentType.paragraph`
* heading-like paragraph units where `extra_metadata.block_type == "heading"`
* table captions represented as paragraph units
* blockquote text represented as paragraph units

Rules:

* Unicode NFC.
* Line ending normalization.
* NBSP to ordinary space.
* Collapse horizontal whitespace within each line.
* Trim each line edges when appropriate.
* Collapse repeated blank lines conservatively.
* Strip outer whitespace.
* Preserve meaningful line breaks.

Do not:

* merge paragraphs across raw units
* rewrite sentences
* remove punctuation
* remove short headings
* infer headings from PDF

## List Normalization

Applies to:

```text
DocumentContentType.list
```

Rules:

* Use prose-like normalization per line.
* Preserve list metadata in raw `extra_metadata`.
* Do not add or infer numbering.
* Do not merge nested list items.
* Do not remove short list items.

## Table Normalization

Applies to:

```text
DocumentContentType.table
```

Only apply table-aware normalization when:

```text
extra_metadata.serialization_format == "tsv_escaped_v1"
```

Rules:

* Preserve real row delimiters: `\n`.
* Preserve real column delimiters: `\t`.
* Preserve escaped cell content semantics:
  * `\\`
  * `\t`
  * `\n`
* Normalize Unicode inside cells.
* Normalize line endings inside escaped cell values safely.
* Do not remove empty cells.
* Do not flatten table into prose.
* Do not collapse real tabs.

Implementation guidance:

* Add a small parse/serialize helper for `tsv_escaped_v1`.
* Do not use broad `split()` or global whitespace collapse.
* Reuse semantics from DOCX/HTML extractor serialization, but avoid importing
  extractor modules.

If table format is unknown:

* Preserve content.
* Optionally warn `unknown_block_type_fallback` or a more specific table warning
  in Phase 3.3+.

## Code Normalization

Applies to:

```text
DocumentContentType.code
```

Rules:

* Unicode NFC when safe.
* Line ending normalization.
* Optional trim of outer blank lines only.
* Preserve indentation.
* Preserve repeated spaces.
* Preserve tabs.

Do not:

* auto-format code
* collapse horizontal whitespace
* convert tabs to spaces
* strip every line

## Unknown Content Type Fallback

If content type is unknown:

* Apply only generic safe Unicode and line ending normalization.
* Preserve content otherwise.
* Defer warning creation to construction stage if warnings are part of public
  `CleaningResult`.

## Tests To Add

Add:

```text
backend/tests/test_cleaning_normalization.py
```

Test categories:

* Unicode NFC.
* Vietnamese Unicode preservation.
* CRLF and CR to LF.
* NBSP handling for prose.
* Horizontal whitespace collapse for prose only.
* Multiline prose preservation.
* Short heading preservation.
* List line handling.
* Table delimiter preservation.
* Table escaped tab/newline/backslash round trip.
* Empty table cells preserved.
* Code indentation preserved.
* Tabs in code preserved.
* Outer blank lines in code trimmed only if configured.
* Unsafe control characters removed.
* Newline preserved.
* Tab preserved for table/code.
* Idempotency for every helper.
* No parser-object imports needed.

## Verification

Run focused tests:

```text
python -m pytest tests/test_cleaning_normalization.py
```

Run related regression:

```text
python -m pytest tests/test_document_schema.py tests/test_extraction_schema.py tests/test_docx_extractor.py tests/test_html_extractor.py tests/test_pdf_extractor.py
```

Run full backend regression:

```text
python -m pytest
```

## Acceptance Criteria

Phase 3.2 is complete when:

* Pure normalization helpers exist.
* Helpers are deterministic and idempotent.
* Content-type-specific behavior is tested.
* Table and code structure are preserved.
* No source-aware filtering is implemented.
* No clean IDs, clean indexes, dropped records, or `CleaningResult` assembly is
  implemented here unless required for test scaffolding.
* No dependencies are added.

## Deferred To Later Sub-Phases

* Blank-unit dropping: Phase 3.3.
* Clean unit creation: Phase 3.3.
* Public `CleaningResult` warnings from normalization: Phase 3.3.
* HTML UI filtering: Phase 3.4.
* PDF page-number handling: Phase 3.4.
* Deduplication: Phase 3.5.
