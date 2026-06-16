

# Phase 3 — Cleaning and Normalization Overview

Status: In Progress

Depends on:

* Phase 1 — Backend contracts and skeleton
* Phase 2 — Source extraction and parsing
* `ExtractionResult`
* `RawDocumentUnit`
* Existing source, document, error, and pipeline schemas

## 1. Purpose

Phase 3 converts structural raw extraction output into deterministic, normalized,
and auditable clean document units suitable for later chunking.

Target flow:

```text
ExtractionResult
  -> RawDocumentUnit[]
  -> Cleaning and normalization
  -> CleaningResult
  -> CleanDocumentUnit[]
```

Phase 3 must improve consistency and remove only high-confidence noise while
preserving document meaning, structure, order, and provenance.

Phase 3 does not create chunks, embeddings, indexes, or generated answers.

## 2. Position in the Pipeline

```text
PDF / DOCX / URL
  -> Phase 2 extraction
  -> RawDocumentUnit[]
  -> Phase 3 cleaning
  -> CleanDocumentUnit[]
  -> Phase 4 chunking
  -> DocumentChunk[]
```

Phase 2 answers:

> What structural content was extracted from the source?

Phase 3 answers:

> Which extracted units should be preserved, normalized, dropped, or marked for
> review before chunking?

## 3. Primary Outputs

Phase 3 must produce:

```text
CleaningResult
├── units: CleanDocumentUnit[]
├── dropped_units: DroppedUnit[]
├── warnings: CleaningWarning[]
└── stats: CleaningStats
```

Successful output must contain at least one clean unit.

If every raw unit is dropped or becomes empty after normalization, the cleaner
must raise a no-content cleaning error instead of returning an empty successful
result.

## 4. Scope

Phase 3 includes:

* Cleaning contracts and invariants.
* Raw-to-clean lineage.
* Deterministic clean unit identifiers and ordering.
* Unicode normalization.
* Line-ending normalization.
* Content-type-aware whitespace normalization.
* Safe control-character handling.
* Blank-unit removal after normalization.
* Conservative source-aware noise filtering.
* Conservative PDF page-number detection and filtering when reliable page
  geometry is available.
* High-confidence HTML UI-noise filtering.
* Conservative exact deduplication.
* Dropped-unit audit records.
* Cleaning warnings and statistics.
* Cleaning application service and error mapping.
* Cross-source verification for DOCX, PDF, and HTML.

## 5. Explicitly Out of Scope

Do not implement:

* Chunk splitting.
* Chunk overlap.
* Token-based chunk sizing.
* Embeddings.
* Vector indexing.
* BM25 indexing.
* Retrieval.
* Reranking.
* Answer generation.
* LLM-based rewriting or classification.
* Summarization.
* Translation.
* Spell correction.
* Semantic paraphrasing.
* OCR.
* PDF reading-order reconstruction.
* PDF table reconstruction.
* JavaScript rendering.
* Multi-page crawling.
* Database persistence.
* API routes.
* Background jobs.
* Domain-specific scraping rules.
* Aggressive semantic deduplication.
* Fuzzy or embedding-based duplicate detection.
* Prompt-injection removal.

## 6. Core Design Principles

### 6.1 Deterministic

The same input, cleaner configuration, and cleaner version must produce the same:

* Clean content.
* Output order.
* Clean IDs.
* Clean indexes.
* Dropped-unit reasons.
* Warnings.
* Statistics.

Processing timestamps may differ between runs if included.

### 6.2 Conservative

When a unit is not clearly noise, preserve it.

```text
High confidence -> drop or modify
Ambiguous       -> preserve and optionally warn
```

Cleaning must prefer false negatives over false positives.

### 6.3 Provenance Preserving

Every clean unit must be traceable to exactly one raw unit in the Phase 3 MVP.

```text
CleanDocumentUnit
  -> raw_unit_id
  -> RawDocumentUnit
  -> source/document/page/section metadata
```

### 6.4 One Raw Unit to Zero or One Clean Unit

Phase 3 MVP uses this relationship:

```text
RawDocumentUnit
  -> zero CleanDocumentUnit
  or
  -> one CleanDocumentUnit
```

Phase 3 must not merge multiple raw units or split one raw unit into multiple
clean units.

Merging and splitting belong to later structural transformation or chunking
phases.

### 6.5 No Silent Dropping

Every dropped raw unit must have an audit record containing:

* `raw_unit_id`
* stable reason code
* short safe message
* original content hash
* source type
* safe metadata when useful

The dropped record must not duplicate the full original content by default.

### 6.6 Content-Type Aware

Paragraph, list, table, and code units must not use the same normalization rules.

Generic operations such as:

```python
" ".join(content.split())
```

must not be applied to all content types because they would destroy table and
code structure.

### 6.7 Source Aware but Parser Independent

Cleaning rules may use:

* `source_type`
* `content_type`
* `extra_metadata.block_type`
* page metadata
* section metadata
* parser provenance

Cleaning code must not import or depend on:

* PyMuPDF objects
* python-docx objects
* BeautifulSoup objects
* HTTPX response objects

## 7. Contracts to Finalize in Phase 3.1

Phase 3.1 must inspect the actual existing `CleanDocumentUnit` schema before
modifying it.

The final contract must support at least:

* Source/document lineage.
* Raw-unit lineage.
* Clean-unit identifier.
* Continuous clean-unit ordering.
* Clean content.
* Page and section provenance.
* Heading path.
* Content type.
* Safe metadata.
* Schema-computed content metrics and hash.

Required first-class `CleanDocumentUnit` fields:

```text
clean_unit_id
clean_unit_index
raw_unit_id
transformations
cleaned_at
```

`clean_unit_index` belongs only to `CleanDocumentUnit`. Do not add it to
`DocumentUnitBase`, `RawDocumentUnit`, or `DocumentChunk`.

The existing `original_character_count` and `removed_character_count` fields
must be removed from `CleanDocumentUnit` in Phase 3.1. Cleaning statistics should
track before/after aggregate character counts instead of storing per-unit
removed-character metrics.

`transformations` is the source of truth for stable machine-readable rule codes
applied to each unit, for example:

```python
transformations=[
    "unicode_nfc",
    "line_endings_normalized",
    "prose_whitespace_normalized",
]
```

Do not duplicate this list in `extra_metadata["cleaning"]["applied_rules"]`.

`cleaned_at` is created by the cleaner implementation. A cleaner run should use
one UTC-aware timestamp for all emitted `CleanDocumentUnit` objects in the same
`CleaningResult`. Runtime timestamps are not stable determinism fields across
separate runs.

### Recommended ID Policy

Because Phase 3 MVP is one-raw-to-zero-or-one-clean, the clean ID should be
derived from raw lineage rather than output position.

Required format:

```text
clean:{document_id}:{raw_unit.unit_index:06d}
```

The clean ID must be derived from `RawDocumentUnit.unit_index`. Do not parse the
`raw_unit_id` string to create `clean_unit_id`.

`clean_unit_id` is stable by raw lineage. `clean_unit_index` is continuous by
cleaning output order.

Example:

```text
Raw indexes:        0, 1, 2, 3
Dropped raw index:     1
Clean indexes:      0,    1, 2
Clean IDs:          clean:document-001:000000
                    clean:document-001:000002
                    clean:document-001:000003
```

This preserves stable lineage while maintaining continuous output order.

## 8. Proposed Cleaning Schemas

Phase 3.1 should create or finalize schemas equivalent to:

### CleaningInput

Contains:

* `source_id`
* `document_id`
* `source_type`
* `units: list[RawDocumentUnit]`
* `cleaner_config`
* `extra_metadata`

Rules:

* Units must be non-empty.
* All units must match input lineage.
* Raw units must already satisfy Phase 2 ordering and ID invariants.
* Unknown fields must be rejected.

### CleaningWarning

Contains:

* stable `warning_code`
* short `message`
* optional `raw_unit_id`
* optional `clean_unit_index`
* stage information if supported
* safe metadata

Warnings must not contain full document content.

### DroppedUnit

Contains:

* `raw_unit_id`
* `reason_code`
* short `message`
* `original_content_hash`
* `source_type`
* safe metadata

### CleaningStats

Core fields should include:

* `total_input_units`
* `total_output_units`
* `dropped_unit_count`
* `modified_unit_count`
* `unchanged_unit_count`
* `warning_count`
* `characters_before`
* `characters_after`
* `extra_metadata`

### CleaningResult

Contains:

* source/document/type lineage
* cleaner name and version
* `units`
* `dropped_units`
* `warnings`
* `stats`

## 9. Cleaning Result Invariants

The successful result validator must enforce:

```text
total_input_units
= total_output_units + dropped_unit_count
```

```text
modified_unit_count + unchanged_unit_count
= total_output_units
```

```text
warning_count
= len(warnings)
```

```text
dropped_unit_count
= len(dropped_units)
```

Additional invariants:

* Clean units are non-empty.
* `clean_unit_id` values are unique.
* `clean_unit_index` is unique, starts at `0`, continuous, and ordered from
  zero.
* The list order of `units` matches `clean_unit_index`.
* Each clean unit references one valid raw unit.
* No raw unit produces more than one clean unit in the MVP.
* Clean-unit relative order follows raw-unit relative order.
* Clean-unit IDs are derived from the referenced raw unit's `unit_index`, not
  from output position.
* All clean units match result lineage.
* Dropped raw IDs do not appear in output clean units.
* Every input raw unit is either emitted or recorded as dropped.
* All clean units in one successful result share one `cleaned_at` timestamp.
* Derived content metrics and hash are generated by schema only.
* Callers cannot provide computed fields.
* Empty successful results are rejected.

## 10. Processing Stage and Errors

Phase 3.1 must inspect the current `ProcessingStage` enum.

Current repository status:

```text
cleaning
```

`ProcessingStage.cleaning` already exists in the current implementation. Phase
3.1 should verify and cover it where needed rather than adding it again.

Proposed error taxonomy:

```text
CleaningError
CleaningInputError
CleaningNoContentError
CleaningLimitError
CleaningInvariantError
```

Rules:

* Known invalid input becomes `CleaningInputError`.
* All units removed becomes `CleaningNoContentError`.
* Resource policy violations become `CleaningLimitError`.
* Invalid final output becomes `CleaningInvariantError`.
* Unexpected implementation bugs must not be hidden by broad exception catches.
* Errors must not include raw content or full document text.

## 11. Cleaner Interface

Recommended provider contract:

```python
class ContentCleaner(Protocol):
    def clean(self, input_data: CleaningInput) -> CleaningResult:
        ...
```

Recommended MVP implementation:

```text
RuleBasedDocumentCleaner
```

The cleaner implementation should accept an injectable clock for deterministic
tests without exposing clock configuration through schemas or service inputs:

```python
RuleBasedDocumentCleaner(
    clock=lambda: datetime.now(timezone.utc),
)
```

Tests may inject a fixed UTC-aware datetime and assert that every emitted clean
unit in the same result uses that exact `cleaned_at` value. `CleaningService`
must not create `cleaned_at`; timestamp creation belongs to the cleaner, similar
to how extractors create `extracted_at`.

The cleaner must be:

* deterministic
* synchronous unless architecture explicitly changes
* policy-driven
* testable without external services
* independent of parser dependencies
* independent of FastAPI and persistence

## 12. Normalization Policy

### 12.1 Unicode

Use Unicode NFC normalization.

Do not use NFKC by default because compatibility normalization may change the
representation or meaning of some characters.

Do not attempt heuristic mojibake repair in the MVP.

Possible mojibake may produce a warning, but content should not be rewritten
without a reliable rule.

### 12.2 Line Endings

Normalize:

```text
CRLF -> LF
CR   -> LF
```

All output text uses `\n`.

### 12.3 Control Characters

Remove only unsafe, non-visible control characters according to an explicit
policy.

Preserve characters required by content structure, especially:

* newline
* tab where meaningful

Do not remove all Unicode format characters without a reviewed policy.

### 12.4 Non-Breaking Spaces

For prose-like content:

```text
NBSP -> ordinary space
```

Table and code policies must remain structure-aware.

## 13. Content-Type-Specific Normalization

### Paragraph and Heading Units

Apply:

* Unicode NFC.
* Line-ending normalization.
* NBSP normalization.
* Horizontal whitespace collapse within each line.
* Outer whitespace stripping.
* Meaningful newline preservation.

Do not:

* rewrite sentences
* lowercase text
* remove punctuation
* merge paragraphs
* correct spelling

Heading units are identified through parser metadata such as:

```text
extra_metadata.block_type = heading
```

Short headings must be preserved.

### List Units

Apply prose-like normalization per line.

Preserve:

* list metadata
* list depth
* ordered/unordered type
* item indexes
* meaningful line breaks

Do not merge list items.

### Table Units

Preserve the `tsv_escaped_v1` contract.

Cleaning may:

* normalize Unicode inside cells
* normalize line endings
* preserve real row and column delimiters

Cleaning must not:

* flatten the table into prose
* collapse real tab delimiters
* remove empty cells
* rebuild table layout heuristically

Prefer a shared table parser/serializer helper rather than unsafe string
splitting.

### Code Units

Preserve:

* indentation
* repeated spaces
* tabs
* line breaks

Only apply:

* Unicode normalization when safe
* line-ending normalization
* optional trimming of outer blank lines

Do not auto-format code.

## 14. Blank Unit Handling

After type-specific normalization:

```text
normalized content is blank
-> drop unit
-> reason_code = empty_after_normalization
```

Blank removal is always audited.

If every unit becomes blank or is dropped, raise `CleaningNoContentError`.

## 15. Source-Aware Noise Filtering

Noise filtering must use multiple signals where possible:

* source type
* content type
* parser block type
* page metadata
* structural metadata
* exact normalized text
* adjacency or repetition

Do not use broad text-only rules when context is required.

## 16. HTML Cleaning Policy

High-confidence HTML noise may include:

* repeated copy/share controls
* reading-time labels
* short UI controls
* exact duplicated container text

Example safe rule:

```text
source_type = url
block_type = container_text
content matches the full reading-time pattern
-> drop: html_reading_time
```

Example:

```text
"7 min read"
-> eligible for removal under the contextual rule
```

The following must not be removed by the same rule:

```text
"This process takes 7 min to read the file."
```

UI strings should be configurable through a cleaning policy rather than
hard-coded throughout the cleaner.

Do not automatically remove related-article text unless structural provenance
provides high-confidence evidence.

Do not implement domain-specific CNN, news-site, or selector rules in the core
MVP.

## 17. PDF Cleaning Policy

High-confidence PDF cleaning may include:

* page-number-only blocks when reliable page geometry is available
* blank layout artifacts
* exact repeated layout noise when evidence is sufficient

A page-number rule must use page provenance and page geometry. Text equality
alone is not sufficient because a standalone number can be a section number,
mathematical value, form value, or real document content.

Auto-drop is allowed only when all required signals are present:

```text
source_type = pdf
normalized content = page number
page_start = page_end
content is a short standalone text block
bbox is valid
page_width and page_height are available and reliable
bbox is in a reviewed page-edge band, such as header or footer
-> drop: pdf_page_number
```

If `bbox` is available but `page_width` or `page_height` is missing, preserve the
unit and optionally emit:

```text
possible_page_number
```

Do not reopen Phase 2 solely to add page dimensions before Phase 3.1-3.3.
Contextual PDF page-number auto-drop may be deferred, or a small PDF metadata
hardening task may be added before Phase 3.4 if real outputs show that page
numbers materially harm chunking.

Preserve:

```text
content = "2026"
page number = 2
```

Do not perform:

* heading inference
* table reconstruction
* equation merging
* multi-column correction
* header/footer removal without sufficient evidence
* hyphenation repair
* OCR

Repeated headers or footers may be flagged rather than dropped when positional
evidence is insufficient.

## 18. DOCX Cleaning Policy

DOCX extraction is usually more structured.

Phase 3 should:

* normalize prose safely
* preserve heading lineage
* preserve captions
* preserve tables
* preserve style and parser metadata when useful
* remove only blank or clearly invalid output

Do not treat DOCX captions or short headings as noise.

Do not infer list numbering beyond existing Phase 2 metadata.

## 19. Deduplication Policy

Deduplication must be conservative and exact in the MVP.

Possible duplicate key:

```text
normalized content
+ content type
+ block type
```

Context may also include:

* section
* page
* adjacency
* source type
* parser metadata

### Eligible High-Confidence Cases

* Adjacent exact duplicate units.
* Repeated HTML UI controls.
* Repeated exact container noise.
* Parser/layout duplication with clear provenance.

### Preserve by Default

* `document_title` and body `heading` units, even when their normalized text is
  identical.
* Repeated headings in different sections.
* Repeated legal clauses.
* Repeated tables on different pages.
* Repeated paragraphs in different document locations.
* Ambiguous non-adjacent duplicates.

Track separately:

```text
exact_duplicate_detected_count
exact_duplicate_dropped_count
possible_duplicate_preserved_count
```

Do not implement:

* Levenshtein deduplication
* semantic similarity
* embedding similarity
* MinHash
* LLM duplicate classification

## 20. Dropped-Unit Reason Codes

Recommended stable codes include:

```text
empty_after_normalization
html_ui_noise
html_reading_time
pdf_page_number
adjacent_exact_duplicate
repeated_ui_duplicate
invalid_structural_unit
```

Reason codes must remain stable for tests, logs, and evaluation.

## 21. Cleaning Warning Codes

Possible warnings include:

```text
replacement_character_detected
possible_mojibake
suspicious_control_characters_removed
possible_page_number
possible_duplicate_preserved
possible_repeated_header
possible_repeated_footer
unknown_block_type_fallback
```

Normal whitespace normalization does not require warnings.

## 22. Resource Limits

Cleaning must have bounded behavior.

Recommended policy fields:

```text
max_input_units
max_input_characters
max_output_units
max_output_characters
```

Exact defaults must be reviewed against current Phase 2 limits.

Example starting point:

```text
max_input_units = 50,000
max_input_characters = 20,000,000
max_output_units = 50,000
max_output_characters = 20,000,000
```

When a limit is exceeded:

```text
raise CleaningLimitError
```

Do not return a partial successful result.

## 23. Metadata Policy

Clean units should preserve useful raw metadata.

Cleaning provenance may be added under a reserved namespace for metadata that is
not already represented by first-class fields, for example:

```json
{
  "cleaning": {
    "cleaner": "rule_based_document_cleaner",
    "cleaner_version": "1.0",
    "modified": true
  }
}
```

Do not store `applied_rules` in metadata. Per-unit rule codes belong only in
`CleanDocumentUnit.transformations`.

Caller or raw metadata must not overwrite service-owned cleaning metadata.

Do not remove parser provenance unless explicitly unnecessary.

Do not store duplicate full raw content in metadata.

## 24. Sub-Phase Breakdown

### Implementation Status

| Sub-phase | Status | Notes |
| --- | --- | --- |
| Phase 3.1 - Cleaning Core Contracts | Completed | Implemented `CleanDocumentUnit.clean_unit_index`, removed per-unit removed-character metrics, added `CleaningInput`, `CleaningWarning`, `DroppedUnit`, `CleaningStats`, `CleaningResult`, cleaning runtime errors, `ContentCleaner` protocol, deterministic clean unit ID helper, and focused contract tests. Full backend regression passed: `342 passed, 2 warnings`. |
| Phase 3.2 - Deterministic Text Normalization | Completed | Implemented pure deterministic normalization helpers, `tsv_escaped_v1` table parse/serialize helpers, content-type dispatch for prose/list/table/code/unknown content, stage-aware control cleanup, internal normalization warnings, and focused idempotency/contract tests. Full backend regression passed: `374 passed, 2 warnings`. |
| Phase 3.3 - Clean Unit Construction | Completed | Implemented `RuleBasedDocumentCleaner`, raw-to-clean candidate finalization, stable clean IDs from `RawDocumentUnit.unit_index`, continuous clean indexes, blank-after-normalization dropped-unit audit records, strict policy/config validation, safe audit metadata, warning finalization, resource limits, UTC timestamp handling, and focused construction tests. Full backend regression passed: `411 passed, 2 warnings`. |
| Phase 3.4 - Source-Aware Filtering | Completed | Implemented conservative source-aware filtering, high-confidence HTML UI-noise and reading-time drops, PDF page-number provenance/bbox validation, footer-only geometry-gated page-number drops, possible page-number warnings for ambiguous edge-like candidates, origin-aware warning stats, safe dropped audit evidence, and false-positive regression tests. Full backend regression passed: `424 passed, 2 warnings`. |
| Phase 3.5 - Conservative Deduplication | Planned | Pending exact normalized duplicate detection, adjacent duplicate handling, source/section/page guards, duplicate audit records, and preservation of ambiguous duplicates. |
| Phase 3.6 - Cleaning Service and Error Boundary | Planned | Pending `CleaningService`, `ExtractionResult -> CleaningInput -> ContentCleaner -> CleaningResult` orchestration, cleaning error mapping to `SourceError`, and service-level integration tests. |
| Phase 3.7 - Final Verification and Documentation | Planned | Pending final cross-source verification, determinism/idempotency checks, lineage/order/statistics verification, limitation documentation, completion report, and Phase 4 input contract. |

### Phase 3.1 — Cleaning Core Contracts

Status: Completed.

Completion notes:

* Added the shared cleaning contracts in `backend/app/schemas/cleaning.py`.
* Added `clean_unit_index` to `CleanDocumentUnit`.
* Removed `original_character_count` and `removed_character_count` from
  `CleanDocumentUnit`.
* Added `CleaningInput`, `CleaningWarning`, `DroppedUnit`, `CleaningStats`, and
  `CleaningResult`.
* Kept `DroppedUnit.unit_index` required and non-negative because every dropped
  record represents one concrete `RawDocumentUnit`.
* Kept `CleaningWarning.clean_unit_index` optional because warnings can be
  emitted before final clean indexes exist, for dropped units, or at run scope.
* Added aggregate validation for raw input order, clean output order, dropped
  unit order, lineage, disjoint emitted/dropped raw IDs, statistics, and one
  `cleaned_at` value per cleaning result.
* Added cleaning runtime error types separately from `SourceError`.
* Added the `ContentCleaner` protocol.
* Added deterministic `clean_unit_id` helper using:
  `clean:{document_id}:{raw_unit.unit_index:06d}`.
* Added focused tests for cleaning schemas, IDs, errors, protocol behavior, and
  updated document schema behavior.
* Verification completed with full backend regression:
  `342 passed, 2 warnings`.

Tasks:

* Audit the current `CleanDocumentUnit`.
* Finalize raw-to-clean lineage.
* Add `clean_unit_index`.
* Remove `original_character_count` and `removed_character_count`.
* Create cleaning schemas.
* Add cleaning error taxonomy.
* Add `ContentCleaner` protocol.
* Verify existing `ProcessingStage.cleaning` behavior.
* Add deterministic clean ID helper.
* Add schema and invariant tests.

No real cleaning rules are implemented.

Output:

```text
Stable cleaning contracts
```

### Phase 3.2 — Deterministic Text Normalization

Status: Completed.

Completion notes:

* Added pure normalization helpers in
  `backend/app/rag/cleaning/normalization.py`.
* Added table text helpers in `backend/app/rag/cleaning/table_text.py` for
  `tsv_escaped_v1` parse/serialize behavior.
* Implemented paragraph, list, table, code, and unknown content normalization.
* Recorded only transformation rule codes that changed output content.
* Implemented stage-aware control cleanup after line-ending normalization and
  content-type whitespace handling.
* Preserved table delimiters, escaped cell semantics, empty cells, code
  indentation, code tabs, repeated code spaces, and code outer blank lines.
* Kept unknown content conservative by preserving tabs and NBSP.
* Added internal warnings for replacement characters and removed unsafe control
  characters.
* Deferred public `CleaningWarning` assembly, blank-unit dropping, clean-unit
  construction, source-aware filtering, and deduplication.
* Added focused tests in `backend/tests/test_cleaning_normalization.py`.
* Verification completed with full backend regression:
  `374 passed, 2 warnings`.

Tasks:

* Implement Unicode NFC normalization.
* Normalize line endings.
* Implement safe control-character policy.
* Normalize NBSP.
* Add prose normalization.
* Add list normalization.
* Add table-safe normalization.
* Add code-preserving normalization.
* Add idempotency tests for pure helpers.

No source-aware noise filtering or deduplication.

Output:

```text
Raw content -> deterministic normalized content
```

### Phase 3.3 — Clean Unit Construction

Status: Completed.

Completion notes:

* Added `RuleBasedDocumentCleaner` and `CleaningPolicy` in
  `backend/app/rag/cleaning/rule_based_cleaner.py`.
* Implemented one-raw-to-zero-or-one-clean construction from `CleaningInput`.
* Implemented deterministic clean IDs from raw unit indexes and continuous
  clean indexes from emitted output order.
* Implemented blank-after-normalization dropped-unit audit records.
* Implemented shared blank helper semantics, including NBSP/Unicode whitespace
  handling and preservation of zero-width/Unicode `Cf`-only content.
* Implemented safe dropped audit using `original_content_hash =
  raw.content_hash` and allowlisted metadata only.
* Implemented strict top-level raw `extra_metadata["cleaning"]` conflict
  rejection.
* Implemented policy precedence and strict `cleaner_config` resource-limit
  override validation.
* Implemented successful-run clock behavior: one call, timezone-aware required,
  non-UTC normalized to UTC, failure paths do not call `clock()`.
* Implemented public cleaning warnings from normalization warnings during
  finalization.
* Implemented cleaning stats and schema invariant equations.
* Added focused tests in
  `backend/tests/test_rule_based_cleaner_construction.py`.
* Verification completed with full backend regression:
  `411 passed, 2 warnings`.

Tasks:

* Implement one-raw-to-zero-or-one-clean conversion.
* Preserve lineage and relative order.
* Generate deterministic clean IDs from `RawDocumentUnit.unit_index`.
* Generate continuous clean indexes.
* Drop blank-after-normalization units.
* Produce dropped-unit audit records.
* Produce cleaning stats.
* Enforce resource limits.
* Use one cleaner-created UTC-aware `cleaned_at` timestamp per result.
* Build validated `CleaningResult`.

No broad UI filtering or deduplication.

Output:

```text
Normalized raw units -> CleanDocumentUnit[]
```

### Phase 3.4 — Source-Aware Filtering

Status: Completed.

Completion notes:

* Added source-aware filtering helpers in
  `backend/app/rag/cleaning/source_filters.py`.
* Added contextual HTML UI-noise and reading-time filtering while preserving
  ambiguous body content, headings, lists, captions, tables, code, and
  non-URL sources.
* Implemented PDF page-number candidate handling with one-based page provenance
  checks and explicit separation from zero-based `page_index`.
* Added strict bbox/page-dimension validation where invalid geometry preserves
  content and never fails the whole cleaning run.
* Implemented footer-only `pdf_page_number` auto-drop when reliable geometry is
  present, header-band preserve/warn behavior, and middle-page silent
  preservation.
* Added internal candidate warning origins for normalization and source-filter
  warnings without changing the public `CleaningWarning` schema.
* Added source-aware stats counters and safe audit metadata for reviewed
  evidence.
* Added focused tests in `backend/tests/test_cleaning_source_filters.py`.
* Verification completed with full backend regression:
  `424 passed, 2 warnings`.

Tasks:

* Add high-confidence HTML UI-noise rules.
* Add reading-time filtering.
* Add contextual PDF page-number warnings or filtering only when page geometry is
  sufficient.
* Add source-aware reason codes and counters.
* Add false-positive regression tests.
* Preserve ambiguous content.

No fuzzy or semantic classification.

Output:

```text
Normalized clean units with high-confidence noise removed
```

### Phase 3.5 — Conservative Deduplication

Status: Planned.

Tasks:

* Detect exact normalized duplicates.
* Implement adjacent exact-duplicate handling.
* Remove repeated high-confidence UI duplicates.
* Preserve ambiguous duplicates.
* Record duplicate audit information.
* Add source, section, page, and block-type guards.

Output:

```text
Clean units without high-confidence duplicate noise
```

### Phase 3.6 — Cleaning Service and Error Boundary

Status: Planned.

Tasks:

* Add `CleaningService`.
* Accept `ExtractionResult`.
* Build `CleaningInput`.
* Inject `ContentCleaner`.
* Map known cleaning errors to `SourceError`.
* Preserve exception chaining.
* Keep the service independent of FastAPI and persistence.
* Add integration tests using Phase 2 outputs.

Output:

```text
ExtractionResult -> CleaningService -> CleaningResult
```

### Phase 3.7 — Final Verification and Documentation

Status: Planned.

Tasks:

* Verify DOCX, PDF, and HTML cleaning behavior.
* Verify determinism.
* Verify normalization idempotency.
* Verify raw-to-clean lineage.
* Verify ordering and clean indexes.
* Verify dropped-unit audit.
* Verify statistics.
* Run smoke tests on real Phase 2 fixtures.
* Document limitations.
* Produce the Phase 4 input contract.

Output:

```text
Phase 3 completion report
Cross-source cleaning matrix
Stable input for Phase 4 chunking
```

## 25. Test Strategy

### Contract Tests

Test:

* valid cleaning input
* valid cleaning result
* unknown-field rejection
* empty-unit rejection
* duplicate clean IDs
* non-continuous clean indexes
* broken raw lineage
* stats mismatch
* warning-count mismatch
* dropped-count mismatch
* computed-field rejection

### Normalization Tests

Test:

* Unicode NFC
* Vietnamese Unicode
* CRLF and CR
* NBSP
* repeated horizontal spaces
* multiline prose
* list text
* table structure preservation
* code indentation preservation
* normalization idempotency

### HTML Tests

Test:

* `Link Copied!`
* reading-time labels
* duplicated UI controls
* normal short paragraph preservation
* related-story text preservation when ambiguous
* metadata-aware filtering

### PDF Tests

Test:

* page-number-only removal when page dimensions and bbox support page-edge
  detection
* page-number candidate preservation with `possible_page_number` warning when
  page dimensions are missing
* numeric content preservation
* repeated footer candidate behavior
* page provenance preservation

### DOCX Tests

Test:

* heading preservation
* caption preservation
* table preservation
* prose normalization
* no fabricated pages

### Deduplication Tests

Test:

* adjacent exact duplicate
* repeated UI duplicate
* same heading in different sections preserved
* same paragraph on different pages preserved when ambiguous
* duplicate counters and dropped audit

### Invariant Tests

Test:

```text
input units = output units + dropped units
modified + unchanged = output units
warning count = warnings length
dropped count = dropped records length
```

### Determinism Tests

Run the same input twice and compare all stable fields.

### Smoke Tests

Use real or previously captured Phase 2 outputs:

* DOCX extraction result.
* PDF extraction result.
* CNN HTML extraction result.

Tests and smoke scripts must not call external websites.

## 26. Cross-Source Cleaning Expectations

| Contract                       | DOCX         | PDF                  | HTML         |
| ------------------------------ | ------------ | -------------------- | ------------ |
| Unicode normalization          | Yes          | Yes                  | Yes          |
| Line-ending normalization      | Yes          | Yes                  | Yes          |
| Prose whitespace normalization | Yes          | Yes                  | Yes          |
| Table structure preserved      | Yes          | N/A                  | Yes          |
| Code structure preserved       | When present | When present         | Yes          |
| Heading lineage preserved      | Yes          | None from extraction | Yes          |
| Page provenance preserved      | None         | Yes                  | None         |
| Page-number filtering          | No           | Geometry-gated       | No           |
| UI-noise filtering             | No           | No                   | Contextual   |
| Exact deduplication            | Conservative | Conservative         | Conservative |
| Raw lineage preserved          | Yes          | Yes                  | Yes          |
| Chunking included              | No           | No                   | No           |

## 27. Known Limitations

Phase 3 does not solve:

* Missing JavaScript-rendered HTML content.
* PDF OCR.
* PDF reading-order errors.
* PDF formulas split across units.
* PDF table reconstruction.
* DOCX image/chart/text-box extraction.
* Semantic related-content classification.
* Prompt-injection detection.
* Near-duplicate detection.
* Domain-specific boilerplate.
* Semantic correction or rewriting.

These limitations must not be hidden by aggressive cleaning.

## 28. Acceptance Criteria

Phase 3 is complete only when:

1. Cleaning contracts are explicit and strict.
2. Raw-to-clean lineage is preserved.
3. Clean IDs are deterministic.
4. Clean indexes are continuous.
5. Relative raw order is preserved.
6. Unicode and line endings are normalized.
7. Paragraph/list/table/code structure is preserved.
8. Blank-after-normalization units are audited and dropped.
9. High-confidence HTML UI noise can be removed.
10. Contextual PDF page numbers can be removed only when reliable page geometry
    is available; otherwise candidates are preserved and may be warned.
11. Ambiguous content is preserved.
12. Exact deduplication is conservative.
13. Every dropped unit has an audit record.
14. Cleaning statistics satisfy all invariants.
15. Resource limits fail without partial output.
16. Known errors map to the cleaning stage.
17. No raw content is exposed in errors.
18. No chunking, embeddings, persistence, or API routes are added.
19. Focused tests pass.
20. Phase 2 regression tests pass.
21. Full backend regression passes.
22. Real Phase 2 fixtures produce reviewable clean output.
23. Phase 4 can consume `CleanDocumentUnit[]` without source-specific parser logic.

## 29. Implementation Rules for Codex

Before each sub-phase:

1. Read `backend/AGENTS.md`.
2. Read `.agents/architecture.md`.
3. Read the Phase 2 overview and completion notes.
4. Read this Phase 3 overview.
5. Read the current task file for the specific Phase 3 sub-phase.
6. Inspect actual schemas and implementation before proposing changes.
7. Prefer existing contracts and helpers over new abstractions.
8. Do not modify unrelated modules.
9. Do not add dependencies without approval.
10. Do not implement later Phase 3 work early.
11. Report schema or architecture conflicts before changing shared contracts.
12. Keep tests deterministic and independent of external services.

After each sub-phase, report:

* Files changed.
* Contract changes.
* Rule behavior.
* Error behavior.
* Focused test result.
* Related regression result.
* Full backend regression result.
* Known limitations.
* Deferred work.

## 30. Final Phase 3 Output

At completion, the system must support:

```text
ExtractionResult
  -> CleaningService
  -> deterministic normalization
  -> conservative filtering
  -> conservative exact deduplication
  -> CleaningResult
  -> CleanDocumentUnit[]
```

The output must be suitable for Phase 4 structure-aware chunking without
requiring Phase 4 to understand DOCX, PDF, HTML, HTTP, or parser-specific
implementation details.
