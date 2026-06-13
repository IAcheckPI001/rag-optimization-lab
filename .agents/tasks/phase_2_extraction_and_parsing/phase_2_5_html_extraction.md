# Phase 2.5: HTML Extraction

Parent phase: `phase_2_source_extraction_overview.md`

Depends on:

* `phase_2_1_extraction_core_contracts.md`
* `phase_2_4_url_fetching.md`

## 1. Purpose

Implement a structural HTML extractor that converts trusted-by-boundary but
untrusted HTML bytes into the existing Phase 2.1 extraction contracts.

Target flow:

```text
FetchedContent
 -> ExtractionService builds ExtractionInput
 -> HtmlExtractor
 -> ExtractionResult
 -> RawDocumentUnit[]
```

Phase 2.5 performs HTML parsing and structural unit extraction only.

It must not fetch URLs, follow links, crawl pages, render JavaScript, sanitize
HTML for browser display, clean boilerplate aggressively, chunk content, embed
content, index content, or map extraction errors into source-level errors.

---

## 2. Scope

Implement:

* `HtmlExtractor` under the extraction provider boundary.
* `beautifulsoup4` as the structural HTML parser dependency.
* HTML input validation for `SourceType.url`.
* Optional HTML/XHTML media type validation when `media_type` is provided.
* Charset handling with deterministic fallback and warning behavior.
* Deterministic root selection.
* DOM-order structural extraction.
* Heading state and heading paths.
* Title, heading, paragraph, list item, table caption, table, blockquote, and
  fallback leaf-container units.
* Deterministic table serialization compatible with DOCX `tsv_escaped_v1`.
* HTML-specific extraction statistics and safe metadata.
* Resource limits for input size, candidate traversal, emitted units, and total
  extracted characters.
* Focused pytest coverage and full backend regression.

Do not implement:

* URL fetching or HTTP logic.
* SSRF, DNS, redirect, robots, or network policy.
* JavaScript rendering.
* Link discovery or multi-page crawling.
* `trafilatura`.
* General cleaning, semantic deduplication, token-based splitting, chunking,
  embedding, indexing, persistence, or API routes.
* New extraction schemas or enum values.

---

## 3. Dependency

Add `beautifulsoup4` as a runtime dependency according to the current
`backend/pyproject.toml` dependency style.

Use Python's built-in `html.parser` through BeautifulSoup for Phase 2.5.

Do not add:

```text
trafilatura
lxml as a new direct dependency
html5lib
Playwright
Selenium
requests
robots.txt parsers
```

Resolve the parser version strictly:

```text
extractor_name = "beautifulsoup4"
extractor_version = importlib.metadata.version("beautifulsoup4")
```

If package metadata is unavailable, raise `ExtractionInvariantError`. Do not
silently return `"unknown"`.

---

## 4. Expected Files

Expected additions or modifications:

```text
backend/pyproject.toml
backend/app/providers/extraction/html_extractor.py
backend/tests/test_html_extractor.py
```

Existing extraction contracts, schemas, and errors should be reused.

No API routes, database models, registry wiring, or extraction service
orchestration should be added in Phase 2.5.

---

## 5. Input Contract

`HtmlExtractor.extract()` receives `ExtractionInput`.

Required behavior:

* Require `input_data.source_type is SourceType.url`.
* Preserve `source_id`, `document_id`, `source_type`, and `source_uri` on every
  emitted `RawDocumentUnit`.
* Use `input_data.content_bytes`; do not read temporary files.
* `source_uri` may be `None`, but if present it must be copied to every unit.
* `content_bytes` must never be placed in exception details, warnings, metadata,
  repr output, or logs.

Media type behavior:

* If `input_data.media_type is None`, allow extraction.
* If provided, allow only:

```text
text/html
application/xhtml+xml
```

* If another media type is provided, raise `ExtractionParsingError`.
* Do not MIME-sniff arbitrary binary content into HTML.

---

## 6. HTML Extraction Policy

Create one internal policy object for hard limits:

```text
max_input_bytes = 5 * 1024 * 1024
max_candidate_blocks = 50_000
max_units = 10_000
max_total_extracted_characters = 5_000_000
```

Limit behavior:

* If `content_bytes` exceeds `max_input_bytes`, raise `ExtractionParsingError`
  before parsing.
* If candidate traversal exceeds `max_candidate_blocks`, raise
  `ExtractionParsingError`.
* If emitting another unit would exceed `max_units`, raise
  `ExtractionParsingError`.
* If total emitted content would exceed `max_total_extracted_characters`, raise
  `ExtractionParsingError`.
* Do not return partial `ExtractionResult` for any limit failure.
* Do not count limit failures as `skipped_items`.

---

## 7. Charset Policy

Use `input_data.charset` when it is valid, but do not fail closed on an invalid
declared charset if BeautifulSoup can still parse the document.

Behavior:

* If `input_data.charset` is provided and `codecs.lookup()` succeeds, pass it as
  `from_encoding`.
* If `input_data.charset` is provided but invalid:
  * Add an `ExtractionWarning` with
    `warning_code="invalid_declared_charset"` and
    `stage=ProcessingStage.parsing`.
  * Parse again without `from_encoding` and allow BeautifulSoup to detect the
    encoding.
* If parsing still fails due to a known parser/decode failure, raise
  `ExtractionParsingError`.

Store charset information once in `stats.extra_metadata`:

```text
declared_charset
declared_charset_valid
detected_encoding
charset_fallback_used
```

Do not repeat charset fields on every unit.

---

## 8. Root Selection

Before root selection, remove or exclude these non-content elements:

```text
script
style
template
noscript
```

They are not candidates. Their descendants must not receive `block_index`, must
not increase `observed_block_count`, and must not increase `skipped_items`.

Root usability:

A root is usable when, after non-content exclusion, it contains at least one
recognized nonblank candidate or visible nonblank text that can become a
fallback candidate.

Selection order:

```text
if exactly one usable <main>:
    use that main
elif exactly one usable <article>:
    use that article
elif <body> exists:
    use body
else:
    use document root
```

If multiple usable `<main>` or multiple usable `<article>` elements exist,
fallback deterministically to `<body>`.

When fallback root is `<body>`, ignore page-level semantic containers:

```text
nav
header
footer
aside
```

Do not use class, id, domain, keyword, or page-specific heuristics.

Ignored semantic containers are not candidates. Their descendants must not
receive `block_index`, must not increase `observed_block_count`, and must not
increase `skipped_items`.

Track:

```text
removed_non_content_tag_count
ignored_semantic_container_count
selected_root_tag
selected_root_strategy
```

---

## 9. Candidate And Index Semantics

A candidate block is a recognized extractable block after:

* non-content exclusion,
* semantic-container ignore rules,
* root selection,
* ownership suppression.

Ownership-suppressed descendants are not candidates and are not skipped items.

Counters:

* `block_index` increments for every candidate, including blank candidates.
* `unit_index` increments only for emitted units.
* `skipped_items` increments only for candidates that are evaluated but not
  emitted, such as blank candidates or recoverable malformed candidates.
* `observed_block_count` equals the number of candidates evaluated.

Successful extraction invariant:

```text
observed_block_count = stats.total_units + stats.skipped_items
stats.total_units = len(units)
stats.warning_count = len(warnings)
```

If no units are emitted, raise `ExtractionNoContentError`; do not return an
empty `ExtractionResult`.

---

## 10. Unit Types

Do not add new `DocumentContentType` enum values.

Use existing content types:

| HTML structure | `content_type` | `extra_metadata.block_type` |
| --- | --- | --- |
| `<title>` | `paragraph` | `document_title` |
| `<h1>`-`<h6>` | `paragraph` | `heading` |
| `<p>` | `paragraph` | `paragraph` |
| `<li>` | `list` | `list_item` |
| `<caption>` | `paragraph` | `table_caption` |
| `<table>` | `table` | `table` |
| `<pre>` or `<pre><code>` | `code` | `code_block` |
| `<blockquote>` direct text | `paragraph` | `blockquote` or `blockquote_text` |
| leaf fallback container | `paragraph` | `container_text` |

Bare `<code>` must not emit an independent unit in Phase 2.5. It is inline text
owned by its parent or fallback text candidate.

---

## 11. Heading And Section Semantics

HTML headings must match the DOCX heading convention:

```text
content_type = DocumentContentType.paragraph
extra_metadata.block_type = "heading"
extra_metadata.heading_level = 1..6
```

Heading behavior:

* Blank headings are skipped.
* Blank headings do not update heading state.
* Nonblank headings update heading state.
* A heading unit's `heading_path` includes itself.
* Non-heading units inherit the current `heading_path`.
* Lower-level heading changes reset deeper levels.
* `section = heading_path[-1] if heading_path else None`.

`<title>` may emit a `document_title` unit before body/root content, but it must
not update heading state.

---

## 12. Text Serialization

For headings, paragraphs, captions, list items, blockquote text, and container
fallback text:

* Decode HTML entities through BeautifulSoup.
* Convert non-breaking spaces to ordinary spaces.
* Preserve `<br>` as newline.
* Collapse horizontal whitespace per line.
* Strip outer whitespace.

For `<pre>` code blocks:

* Preserve newlines.
* Preserve indentation.
* Preserve repeated spaces.
* Trim only outer blank lines.

Do not use a generic `get_text(" ", strip=True)` for code blocks.

---

## 13. List Strategy

Use list item units.

Each valid `<li>` candidate may emit one `RawDocumentUnit`.

Direct list item serialization:

* Serialize all text owned by the current `<li>`.
* Include inline tags and paragraph descendants.
* Exclude descendant `<ul>` and `<ol>` subtrees.
* For MVP, if an `<li>` contains a table or `<pre>`, the list item owns that
  content as serialized text; nested table/code units inside list items are not
  emitted independently.

Counters:

* `list_container_global_index` increments for every observed `<ul>` or `<ol>`
  after exclusion and ownership rules, even if none of its items emit.
* `list_item_global_index` increments for every `<li>` candidate, including
  blank skipped items.
* `list_item_index_in_container` is the zero-based position in the direct parent
  list.
* `list_depth` starts at `0` for root lists.
* `list_type` is `ordered` for `<ol>` and `unordered` for `<ul>`.
* `parent_emitted_list_item_global_index` is set only when the nearest parent
  `<li>` emitted a unit; otherwise it is `None`.

A blank parent `<li>` does not block valid nested child `<li>` units.

---

## 14. Table Strategy

HTML table units must use the same serialization semantics as DOCX
`tsv_escaped_v1`.

Cell escaping:

```text
backslash -> \\
CRLF/CR   -> LF
tab       -> \t
newline   -> \n
```

Rows are joined with real newline characters. Cells are joined with real tab
characters.

Rules:

* `th` and `td` both count as cells.
* Empty cells serialize as an empty string.
* Uneven rows are preserved.
* `row_count` is the number of direct rows in the current table.
* `column_count` is `max(row_column_counts)`.
* `row_column_counts` records the number of direct cells per row.
* Blank table detection uses raw direct cell text before TSV escaping.

Do not use unrestricted `table.find_all("tr")`, because that can include nested
table rows.

Only direct rows and direct cells belonging to the current table should
contribute to row and cell counts.

Table metadata:

```text
block_type
block_index
table_index
row_count
column_count
row_column_counts
serialization_format = "tsv_escaped_v1"
```

---

## 15. Caption Policy

Use one policy: table captions are separate candidates and separate units.

Behavior:

* A nonblank `<caption>` emits a paragraph unit with
  `block_type="table_caption"`.
* The table emits a separate table unit after the caption.
* A blank caption receives its own `block_index` and increments
  `skipped_items`.
* The table still receives the next `block_index` and is processed normally.
* The caption text must not be folded into the TSV table content.

This keeps:

```text
observed_block_count = stats.total_units + stats.skipped_items
```

---

## 16. Nested Table Policy

Use one policy: an outer table owns its direct cell content, and nested tables
are ignored as nested structures in Phase 2.5.

Behavior:

* Nested tables inside a table do not emit independent units.
* Nested tables do not receive `block_index`.
* Nested tables do not increase `skipped_items`.
* When serializing an outer cell, exclude descendant nested `<table>` subtrees.
* Nested table rows and cells must not contribute to the outer table's
  `row_count`, `column_count`, or `row_column_counts`.
* Track `nested_table_ignored_count`.
* Do not emit warnings by default for nested tables.

---

## 17. Blockquote Policy

`<blockquote>` must preserve DOM order and avoid duplicate ownership.

Behavior:

* If a blockquote contains recognized child blocks, process children in DOM
  order.
* Recognized child units inside blockquote should include:

```text
nearest_semantic_container = "blockquote"
```

* Loose direct text nodes inside blockquote must emit `blockquote_text`
  candidates at their DOM positions.
* If a blockquote has no recognized child blocks but has nonblank direct text,
  emit one `blockquote` paragraph unit.
* Blank blockquote candidates increment `skipped_items`.

Do not flatten a blockquote when doing so would duplicate child blocks or lose
DOM order.

---

## 18. Fallback Container Text

Do not emit every `<div>`, `<section>`, or `<article>` as a unit.

Emit a fallback `container_text` candidate only when:

* the element has nonblank direct visible text,
* the element does not contain recognized block descendants that own the text,
* the element is not inside an ignored semantic container,
* emitting it will not duplicate a parent-owned candidate.

This allows simple HTML such as:

```html
<div>Hello world</div>
```

to produce a unit without turning layout wrappers into noisy units.

---

## 19. Unit Metadata

Common unit metadata:

```text
parser
parser_version
block_type
block_index
html_tag
```

Add fields where relevant:

```text
heading_level
heading_index
paragraph_index
list_container_global_index
list_item_global_index
list_item_index_in_container
list_depth
list_type
parent_emitted_list_item_global_index
table_index
row_count
column_count
row_column_counts
serialization_format
code_block_index
nearest_semantic_container
```

Do not store full HTML, raw bytes, query strings, fragments, or credentials in
unit metadata.

---

## 20. Stats Metadata

`ExtractionStats.extra_metadata` should stay statistics-oriented.

Include:

```text
selected_root_tag
selected_root_strategy
declared_charset
declared_charset_valid
detected_encoding
charset_fallback_used
removed_non_content_tag_count
ignored_semantic_container_count
nested_table_ignored_count
observed_block_count
emitted_title_count
emitted_heading_count
emitted_paragraph_count
emitted_list_item_count
emitted_caption_count
emitted_table_count
emitted_code_block_count
emitted_blockquote_text_count
emitted_container_text_count
```

Do not use stats metadata as a generic provenance dump.

---

## 21. Error Handling

Use narrow exception handling.

Raise:

* `ExtractionSourceTypeMismatchError` for non-URL source types.
* `ExtractionParsingError` for unsupported media type, parser/decode failure,
  malformed HTML failures that cannot continue, and hard resource limit
  failures.
* `ExtractionNoContentError` when parsing succeeds but no nonblank units are
  emitted.
* `ExtractionInvariantError` when the extractor produces an invalid
  `ExtractionResult`.

Do not catch broad `Exception`.

Do not wrap existing `ExtractionError` subclasses again.

Only wrap `pydantic.ValidationError` from final `ExtractionResult` construction
as `ExtractionInvariantError`, preserving the original exception as `__cause__`.

Implementation bugs such as unexpected `TypeError`, `AttributeError`, or
unexpected `KeyError` should surface in tests instead of being hidden as parser
errors unless a specific parser-input case is intentionally handled.

---

## 22. Expected Result Construction

Use the same successful result pattern as DOCX and PDF extractors:

* Create one `extracted_at = datetime.now(timezone.utc)` per extraction run.
* Use the same timestamp for every unit in the result.
* Use `unit_index=len(units)` for emitted units.
* Use `build_raw_unit_id(input_data.document_id, unit_index)`.
* Do not manually set computed fields such as `character_count`, `word_count`,
  or `content_hash`.
* Let `ExtractionResult` validate lineage, index ordering, uniqueness, and
  stats consistency.

---

## 23. Tests

Add focused tests under `backend/tests/test_html_extractor.py`.

Required scenarios:

* Valid HTML with title, headings, paragraphs, lists, caption, table,
  blockquote, and preformatted code.
* Wrong source type raises `ExtractionSourceTypeMismatchError`.
* Unsupported provided media type raises `ExtractionParsingError`.
* Missing media type is allowed.
* `source_uri` is preserved on every unit.
* Common timestamp across all units.
* Deterministic `raw_unit_id` and continuous ordered `unit_index`.
* Heading state, section, and heading path behavior.
* Blank heading does not update heading state.
* Invalid declared charset creates `invalid_declared_charset` warning and
  fallback parsing.
* Charset metadata appears in `stats.extra_metadata`, not every unit.
* Root selection chooses one usable main, one usable article, or deterministic
  body fallback.
* Empty main does not hide usable article/body content.
* Body fallback ignores page-level `nav`, `header`, `footer`, and `aside`
  without counting them as skipped candidates.
* Non-content tags do not create candidates or skipped items.
* List item direct-content serialization excludes nested lists.
* List indexes are stable for emitted and skipped list items.
* Parent blank list item does not prevent nested child item emission.
* Caption and table are separate candidates with separate `block_index` values.
* Blank caption increments `skipped_items`; table still processes.
* Table TSV escaping matches DOCX semantics for tabs, newlines, and backslashes.
* Uneven table rows produce deterministic row metadata.
* Nested tables are ignored without duplicate text or row/cell count pollution.
* Blockquote direct loose text and child blocks preserve DOM order.
* Bare `<code>` does not emit an independent unit.
* `<pre><code>` emits one code unit.
* Leaf container fallback emits simple direct text without duplicating child
  block content.
* Empty or no-content HTML raises `ExtractionNoContentError`.
* Resource limits raise `ExtractionParsingError` without partial results.
* Final `ExtractionResult` validation failures wrap as `ExtractionInvariantError`.

Run:

```text
pytest
```

---

## 24. Acceptance Criteria

Phase 2.5 is complete when:

* `HtmlExtractor` implements the existing `ContentExtractor` contract.
* HTML extraction remains separate from Phase 2.4 URL fetching.
* No network calls occur in the extractor or tests.
* Units preserve source/document lineage and DOM order.
* Heading, list, table, caption, blockquote, and fallback container behavior are
  deterministic and covered by tests.
* Result stats satisfy Phase 2.1 invariants.
* Invalid charset fallback is warning-based and test-covered.
* Ignored semantic containers are not counted as skipped candidates.
* DOCX-compatible table TSV escaping is test-covered.
* No cleaning, chunking, embedding, indexing, persistence, API routes, or
  registry/service wiring is added.
* Full backend regression passes.
