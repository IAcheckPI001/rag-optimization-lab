# Phase 3.4 - Source-Aware Filtering

Status: Planned.

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

Source filtering should run after deterministic normalization and before clean
unit emission for each raw unit.

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
bbox is in reviewed header/footer edge band
```

If `bbox` exists but `page_width` or `page_height` is missing:

```text
preserve unit
optional warning = possible_page_number
```

Given current Phase 2 metadata, default implementation should preserve and warn
rather than auto-drop.

Do not reopen Phase 2 inside Phase 3.4 unless explicitly approved as a small PDF
metadata hardening task.

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
* preserved candidate emits `possible_page_number` warning if policy enables it.
* standalone number that does not match page number preserved.
* `2026` on page 2 preserved.
* with synthetic page dimensions and footer bbox, `pdf_page_number` can be
  dropped.
* missing/invalid bbox preserves content.
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

