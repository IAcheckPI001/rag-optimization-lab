# Phase 3.5 - Conservative Deduplication

Status: Planned.

Depends on:

* Phase 3.4 source-aware filtering.

## Purpose

Add conservative exact deduplication after deterministic normalization and
source-aware filtering.

This phase removes only high-confidence duplicate noise and preserves ambiguous
repetition.

Do not implement:

* fuzzy string matching
* Levenshtein distance
* MinHash
* embedding similarity
* semantic similarity
* LLM duplicate classification
* BM25/hybrid retrieval
* reranking
* chunking

## Current Implementation Facts

Phase 2 can emit repeated content for legitimate reasons:

* repeated DOCX headings in different sections
* repeated legal clauses
* repeated table structures
* repeated PDF headers/footers without reliable geometry
* HTML title and H1 with similar or identical text
* repeated UI controls in HTML

Dedup must not rely on normalized text alone.

## Deduplication Timing

Run dedup after:

```text
normalization
source-aware filtering
blank-after-normalization dropping
```

But before final clean indexes are assigned, or rebuild clean indexes after any
dedup drops.

Recommended implementation:

* process raw units into intermediate keep/drop decisions
* apply dedup decisions
* assign final continuous `clean_unit_index` only after all drops

This avoids index churn inside the same run.

## Exact Duplicate Key

Base duplicate key:

```text
normalized content
content_type
extra_metadata.block_type
```

Additional context for preservation decisions:

```text
source_type
section
heading_path
page_start/page_end
html_tag
nearest_semantic_container
serialization_format
```

Do not use content hashes alone unless the hash is computed over normalized
content plus relevant structural fields.

## Drop-Eligible Cases

### Adjacent Exact Duplicate

Eligible only when:

```text
same normalized content
same content_type
same block_type
adjacent in raw order after prior filtering
same source_type
not table by default
not heading by default
```

Reason code:

```text
adjacent_exact_duplicate
```

### Repeated UI Duplicate

Eligible when:

```text
source_type = url
content matches configured UI noise
block_type/provenance supports UI control
same exact normalized text repeats
```

Reason code:

```text
repeated_ui_duplicate
```

This should complement Phase 3.4, not replace contextual UI filtering.

## Preserve By Default

Always preserve unless a high-confidence rule says otherwise:

* `document_title` and body `heading` duplicates.
* headings in different sections.
* repeated legal clauses.
* repeated table content.
* repeated paragraphs on different pages.
* repeated paragraphs in different sections.
* non-adjacent duplicate prose.
* PDF repeated headers/footers without sufficient position evidence.

## Warnings And Counters

Warnings:

```text
possible_duplicate_preserved
```

Stats counters under `stats.extra_metadata`:

```text
exact_duplicate_detected_count
exact_duplicate_dropped_count
possible_duplicate_preserved_count
adjacent_exact_duplicate_dropped_count
repeated_ui_duplicate_dropped_count
```

Dropped records must not include full content.

## Impact On Clean IDs And Indexes

Dropped duplicates do not change `clean_unit_id` for remaining units because IDs
derive from raw unit indexes.

Clean indexes must be continuous after deduplication:

```text
raw indexes:    0, 1, 2, 3
drop raw 1, 2
clean indexes:  0,    1
clean IDs:      clean:doc:000000, clean:doc:000003
```

## Tests To Add

Add:

```text
backend/tests/test_cleaning_deduplication.py
```

Test categories:

* adjacent exact duplicate paragraph dropped.
* dropped duplicate has `adjacent_exact_duplicate` audit record.
* remaining clean indexes continuous.
* remaining clean IDs stable by raw unit indexes.
* non-adjacent duplicate prose preserved.
* same heading in different sections preserved.
* `document_title` and `heading` identical text preserved.
* same paragraph on different pages preserved.
* repeated table content preserved.
* repeated UI duplicate dropped only with HTML UI provenance.
* possible duplicate preserved warning emitted when configured.
* stats counters updated.
* deterministic output across repeated runs with fixed clock.

## Verification

Run focused tests:

```text
python -m pytest tests/test_cleaning_deduplication.py
```

Run related tests:

```text
python -m pytest tests/test_rule_based_cleaner_construction.py tests/test_cleaning_source_filters.py
```

Run full backend regression:

```text
python -m pytest
```

## Acceptance Criteria

Phase 3.5 is complete when:

* Exact duplicate detection is deterministic.
* Only high-confidence duplicates are dropped.
* Ambiguous duplicates are preserved.
* Dropped duplicates are audited.
* Duplicate stats are exposed safely.
* Clean IDs remain raw-lineage stable.
* Clean indexes remain continuous.
* No fuzzy, semantic, or embedding-based deduplication is added.
* No dependencies are added.

## Deferred

* Near-duplicate detection is post-MVP.
* Semantic boilerplate removal is out of MVP.
* Retrieval-level duplicate handling belongs to retrieval/evaluation phases, not
  cleaning.

