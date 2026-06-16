# Phase 3.4 - Source-Aware Filtering

Status: Completed.

Completion notes:

* Added source-aware filtering helpers in
  `backend/app/rag/cleaning/source_filters.py`.
* Added high-confidence HTML UI-noise filtering for a small exact allowlist:
  `Link Copied!`, `Copy Link`, `Share`, and `Share this article`.
* Added contextual HTML reading-time filtering for full reading-time labels
  only.
* Preserved ambiguous HTML content, non-URL sources, normal paragraph/list/body
  heading provenance, and duplicate `document_title`/body heading content.
* Added PDF page-number candidate handling with one-based page provenance
  checks and explicit separation from zero-based `page_index`.
* Added strict PDF bbox and page-dimension validation. Invalid geometry now
  preserves content and never fails the whole cleaning run.
* Implemented footer-only `pdf_page_number` auto-drop when synthetic reliable
  geometry proves the unit is a footer page number.
* Preserved and warned for header-band page-number candidates.
* Preserved middle-page page-number-like content silently to avoid
  false-positive audit noise.
* Added internal `_CandidateWarning` and `_WarningOrigin` handling so
  normalization warnings and source-filter warnings share one finalization path
  while stats remain origin-aware.
* Updated cleaning stats with source-aware drop counters and separate
  normalization/source-filter warning counters.
* Extended dropped-unit safe audit metadata allowlist for reviewed source-filter
  evidence such as `bbox`, `page_index`, `page_width`, `page_height`, and
  `nearest_semantic_container`.
* Added focused tests in `backend/tests/test_cleaning_source_filters.py`.
* Verification completed with full backend regression:
  `424 passed, 2 warnings`.

Depends on:

* Phase 3.3 `RuleBasedDocumentCleaner`.
* Normalization, clean-unit construction, dropped audit records, stats, and
  warnings.

## Purpose

Add conservative source-aware filtering for high-confidence noise while
preserving ambiguous content.

Initial source-aware filtering covers:

* high-confidence HTML UI noise
* HTML reading-time labels
* PDF page-number candidates

No fuzzy matching, semantic classification, LLM-based filtering, domain-specific
site rules, crawler behavior, Playwright behavior, chunking, embedding, indexing,
retrieval, or generation is implemented.

## Current Implementation Facts

Phase 2 HTML extraction already:

* removes `script`, `style`, `template`, and `noscript`
* may ignore page-level `nav`, `header`, `footer`, `aside` under body fallback
* emits `document_title`
* emits semantic headings as `content_type=paragraph` and
  `extra_metadata.block_type=heading`
* emits leaf fallback `container_text`
* emits list, table, caption, code, blockquote units
* does not crawl multiple pages

Phase 2 PDF extraction currently provides:

* `page_start`
* `page_end`
* `extra_metadata.page_number`
* `extra_metadata.page_block_index`
* `extra_metadata.document_block_index`
* `extra_metadata.bbox`

Phase 2 PDF extraction does not currently provide:

```text
page_width
page_height
```

Therefore PDF page-number auto-drop must be geometry-gated and may be deferred.

## Proposed Implementation

Extend the cleaner policy and rule pipeline in:

```text
backend/app/rag/cleaning/rule_based_cleaner.py
```

Optional helper module:

```text
backend/app/rag/cleaning/source_filters.py
```

Prefer this helper module if the source-aware implementation makes
`rule_based_cleaner.py` substantially longer. Source filtering should remain
pure, parser-object independent, and internal to the cleaning package.

Source filtering should run after deterministic normalization and before clean
unit emission for each raw unit.

Do not add a public source-filter schema in Phase 3.4. Source filtering is an
internal cleaner decision layer that must still produce the existing public
contracts:

```text
CleaningResult
├── CleanDocumentUnit[]
├── DroppedUnit[]
├── CleaningWarning[]
└── CleaningStats
```

### Candidate Warning Model

Phase 3.3 candidates currently carry the raw unit, normalized content, and an
optional drop decision. Phase 3.4 should extend the internal candidate shape
with a general warning collection rather than adding source-specific warning
fields.

Recommended internal shape:

```python
class _WarningOrigin(str, Enum):
    normalization = "normalization"
    source_filter = "source_filter"
    deduplication = "deduplication"


@dataclass(frozen=True)
class _CandidateWarning:
    warning_code: str
    message: str
    extra_metadata: Mapping[str, object]
    origin: _WarningOrigin


@dataclass(frozen=True)
class _CleanCandidate:
    raw_unit: RawDocumentUnit
    normalized: NormalizedContent
    drop: _DropDecision | None = None
    candidate_warnings: tuple[_CandidateWarning, ...] = ()
```

Mapping rule:

```text
NormalizedContent.warnings
-> _CandidateWarning(origin=normalization)
```

Source-aware rules append warnings with:

```text
origin=source_filter
```

Rationale:

* The finalizer processes one warning collection.
* Stats can still distinguish warning origin.
* Phase 3.5 can add `deduplication` warnings without changing candidate shape.
* `origin` remains internal and must not be added to the public
  `CleaningWarning` schema in Phase 3.4.

### Filter Decision Model

Rule result shape can be internal:

```python
@dataclass(frozen=True)
class FilterDecision:
    action: Literal["preserve", "drop", "warn"]
    reason_code: str | None = None
    warning_code: str | None = None
    message: str | None = None
    extra_metadata: Mapping[str, object] = field(default_factory=dict)
```

Do not expose this as public schema unless needed.

If this shape is used, it should be converted into either:

```text
_DropDecision
```

or:

```text
_CandidateWarning(origin=source_filter)
```

before finalization.

### Policy Surface

Keep the Phase 3.4 policy surface intentionally small.

Do not add a field named:

```python
enable_pdf_page_number_drop: bool = True
```

because it can be misread as meaning that real Phase 2 PDF outputs will drop
page numbers by default. Current Phase 2 PDF metadata does not include page
dimensions, so real extracted page-number candidates are preserved by default.

PDF page-number dropping should be geometry-gated by the metadata itself:

```text
page_width and page_height present and reliable
-> geometry rule may drop

page_width or page_height missing
-> preserve and optionally warn
```

For Phase 3.4, prefer module constants for geometry thresholds instead of
adding constructor policy fields:

```python
PDF_HEADER_BAND_RATIO = 0.10
PDF_FOOTER_BAND_RATIO = 0.10
```

These constants can become policy fields later if dataset review shows a real
need for tuning.

## HTML Filtering Policy

High-confidence HTML filtering may use:

```text
source_type = url
content_type
extra_metadata.block_type
extra_metadata.html_tag
extra_metadata.nearest_semantic_container
normalized content
```

### Reading Time

Drop only full reading-time labels in contextual HTML units.

Eligible example:

```text
source_type = url
block_type = container_text
normalized content fully matches reading-time pattern
```

Reason code:

```text
html_reading_time
```

Examples eligible for drop:

```text
7 min read
7 minute read
1 min read
```

Examples not eligible:

```text
This process takes 7 min to read the file.
Reading time is important for UX.
```

### UI Noise

Drop only configurable, exact, short UI strings with HTML provenance.

Reason code:

```text
html_ui_noise
```

Potential default policy entries:

```text
Link Copied!
Copy Link
Share
Share this article
```

Keep the initial allowlist intentionally small. Do not add broad labels such as
`Related`, `More`, or `Read more` in Phase 3.4 because they can be legitimate
body text, headings, or navigation context without stronger provenance.

Constraints:

* Must require `source_type=url`.
* Should require contextual block type such as `container_text` or another
  reviewed UI-like provenance.
* Do not drop normal paragraph/list/body heading content based only on text.
* Do not implement CNN/news-site/domain selectors.
* Do not remove related-article text without stronger structural provenance.

### HTML Title And H1 Preservation

Do not auto-drop either unit when:

```text
block_type = document_title
block_type = heading
normalized text identical
```

Rationale:

* `document_title` is document metadata-like.
* body heading is structural content.
* body heading updates heading lineage.
* title often contains suffixes and is not guaranteed duplicate.

## PDF Page-Number Policy

Text equality alone is unsafe. A standalone number can be:

* real page number
* section number
* math value
* form value
* table value

Auto-drop `pdf_page_number` only when all are true:

```text
source_type = pdf
normalized content is exactly page number
page_start == page_end
content is a short standalone text block
valid bbox exists
page_width and page_height exist and are reliable
bbox is in reviewed footer edge band
```

If `bbox` exists but `page_width` or `page_height` is missing:

```text
preserve unit
emit warning = possible_page_number
```

Given current Phase 2 metadata, default implementation should preserve and warn
rather than auto-drop.

Do not reopen Phase 2 inside Phase 3.4 unless explicitly approved as a small PDF
metadata hardening task.

### PDF Page Provenance

PDF page-number filtering must first prove that page provenance is internally
consistent.

Phase 2 currently emits PDF page values as:

```text
RawDocumentUnit.page_start = one-based public page number
RawDocumentUnit.page_end = one-based public page number
extra_metadata.page_number = one-based public page number
extra_metadata.page_index = zero-based parser page index
```

`page_index` is parser/debug metadata only. Do not compare `page_index` directly
with normalized content.

Required provenance for `pdf_page_number` auto-drop:

```text
raw.source_type = pdf
raw.page_start is not None
raw.page_end is not None
raw.page_start == raw.page_end
extra_metadata.page_number is an int, not bool
extra_metadata.page_number == raw.page_start
normalized content == str(extra_metadata.page_number)
```

Do not auto-drop these variants in Phase 3.4:

```text
02
- 2 -
Page 2
2 / 10
Page 2 of 10
II
```

If page provenance is missing or inconsistent, preserve the unit. Missing or
inconsistent page provenance is not a cleaning error because page metadata is
supporting evidence, not a required `RawDocumentUnit` invariant.

### Geometry Reliability

PDF page-number auto-drop is allowed only when page geometry is reliable.

Required metadata:

```text
extra_metadata.bbox
extra_metadata.page_width
extra_metadata.page_height
```

`bbox` must be a list or tuple containing exactly four finite real numbers:

```text
[x0, y0, x1, y1]
```

Reject as unreliable:

```text
missing bbox
non-list/non-tuple bbox
wrong-length bbox
string bbox values
None
NaN
Infinity
bool values
```

Required bbox invariants:

```text
x0 < x1
y0 < y1
0 <= x0 <= page_width
0 <= x1 <= page_width
0 <= y0 <= page_height
0 <= y1 <= page_height
```

Required page dimension invariants:

```text
page_width > 0
page_height > 0
```

Reject bool, NaN, infinity, zero, and negative page dimensions.

Coordinate interpretation follows PyMuPDF-style page coordinates:

```text
x increases left to right
y increases top to bottom
bbox = [x0, y0, x1, y1]
```

Recommended edge-band constants:

```python
PDF_HEADER_BAND_RATIO = 0.10
PDF_FOOTER_BAND_RATIO = 0.10
```

Header/footer membership:

```text
header candidate -> bbox bottom <= page_height * PDF_HEADER_BAND_RATIO
footer candidate -> bbox top >= page_height * (1 - PDF_FOOTER_BAND_RATIO)
```

Only footer-band membership is eligible for auto-drop in Phase 3.4.
Header-band standalone numbers must be preserved and may emit
`possible_page_number`, because top-of-page numbers can be real section
headings, outline numbers, form values, or document content.

If any geometry value is missing, malformed, non-finite, or outside these
invariants, preserve the unit. Invalid bbox or invalid page dimensions must not
fail the whole cleaning run.

### Possible Page-Number Warning

Emit `possible_page_number` only when page provenance is consistent, normalized
content equals the one-based page number, and there is edge-like evidence that
cannot be confirmed strongly enough for auto-drop.

Warn when one of these is true:

```text
bbox exists but page_width or page_height is missing
bbox is in the header band
bbox appears edge-like but geometry is incomplete or invalid
```

Do not warn when valid geometry places the bbox in the middle of the page:

```text
content = "2"
page_number = 2
valid bbox in page middle
-> preserve silently
```

Warning code:

```text
warning_code = possible_page_number
origin = source_filter
```

Recommended warning metadata:

```text
page_number
page_start
page_end
has_bbox
has_page_dimensions
geometry_status
edge_band
```

Do not include full content in the warning metadata.

## Dropped Unit Records

Dropped source-aware units must produce `DroppedUnit` audit records with:

```text
reason_code = html_ui_noise | html_reading_time | pdf_page_number
original_content_hash = raw.content_hash
safe metadata
```

Do not include full content.

Stats should add counters under `stats.extra_metadata`, for example:

```text
html_ui_noise_dropped_count
html_reading_time_dropped_count
possible_page_number_warning_count
pdf_page_number_dropped_count
```

Phase 3.4 must also correct the existing Phase 3.3 warning counter split:

```text
normalization_warning_count
source_filter_warning_count
```

`warning_count` remains the public aggregate invariant and must equal:

```text
len(CleaningResult.warnings)
```

`normalization_warning_count` must count only candidate warnings with:

```text
origin = normalization
```

`source_filter_warning_count` must count only candidate warnings with:

```text
origin = source_filter
```

Do not continue using `len(warnings)` as the value for
`normalization_warning_count` once source-aware warnings exist.

### Safe Audit Metadata

Phase 3.4 should keep the dropped audit allowlist conservative while preserving
the evidence needed to understand source-aware drops.

Recommended additional safe keys:

```text
bbox
page_index
page_width
page_height
nearest_semantic_container
```

The cleaner must still not copy full raw content, raw bytes, URLs with unsafe
tokens, parser objects, or arbitrary caller metadata into dropped audit records.

## Tests To Add

Add:

```text
backend/tests/test_cleaning_source_filters.py
```

HTML tests:

* `Link Copied!` dropped only with URL/container provenance.
* Same text preserved when source type is DOCX/PDF.
* Same text preserved when content type/provenance indicates normal paragraph.
* `7 min read` dropped only as full reading-time label.
* Sentence containing `7 min read` preserved.
* related-story text preserved when ambiguous.
* `document_title` and `heading` with identical text both preserved.
* dropped HTML units create safe audit records.
* stats counters updated.

PDF tests:

* page-number candidate with bbox but missing page dimensions is preserved.
* preserved candidate emits `possible_page_number` warning by default.
* `page_index` is never compared with normalized page-number text.
* inconsistent `page_number`, `page_start`, and `page_end` provenance preserves
  content.
* standalone number that does not match page number preserved.
* `2026` on page 2 preserved.
* with synthetic page dimensions and footer bbox, `pdf_page_number` can be
  dropped.
* synthetic header-band page-number candidate is preserved and warned.
* valid middle-page bbox with page-number-like content is preserved silently.
* missing/invalid bbox preserves content and does not fail the cleaning run.
* repeated footer candidate behavior remains warning/preserve unless evidence is
  sufficient.

Regression tests:

* DOCX headings preserved.
* DOCX captions/short paragraphs preserved.
* HTML body headings preserved.
* HTML table/caption/code/list units preserved unless explicit noise rule
  applies.

## Verification

Run focused tests:

```text
python -m pytest tests/test_cleaning_source_filters.py
```

Run related tests:

```text
python -m pytest tests/test_rule_based_cleaner_construction.py tests/test_html_extractor.py tests/test_pdf_extractor.py tests/test_docx_extractor.py
```

Run full backend regression:

```text
python -m pytest
```

## Acceptance Criteria

Phase 3.4 is complete when:

* HTML UI-noise filtering is contextual and conservative.
* HTML reading-time filtering does not remove sentence content.
* HTML `document_title` and body `heading` duplicates are preserved.
* PDF page-number candidates are not auto-dropped without reliable page
  geometry.
* Source-aware drops are audited.
* Ambiguous content is preserved.
* No domain-specific site rules are implemented.
* No fuzzy, semantic, or LLM filtering is implemented.
* No dependencies are added.

## Deferred To Later Sub-Phases

* Exact deduplication: Phase 3.5.
* Optional PDF extractor page-dimension hardening: separate approved task before
  or during Phase 3.4 only if needed.
* Any domain-specific boilerplate filtering: out of MVP unless explicitly
  requested.
