# Phase 3.3 - Clean Unit Construction

Status: Planned.

Depends on:

* Phase 3.1 cleaning contracts.
* Phase 3.2 deterministic normalization helpers.

## Purpose

Implement the first real cleaner behavior:

```text
CleaningInput
  -> normalize each RawDocumentUnit
  -> drop units that become blank
  -> build CleanDocumentUnit objects
  -> build DroppedUnit audit records
  -> build CleaningStats
  -> return validated CleaningResult
```

This phase keeps the MVP one-raw-to-zero-or-one-clean relationship.

No source-aware HTML UI filtering, PDF page-number filtering, deduplication,
service orchestration, API route, database persistence, chunking, embedding,
indexing, retrieval, or generation is implemented.

## Current Implementation Facts

All Phase 2 extractors already reject blank raw units. Phase 3.3 still needs
blank-after-normalization handling because normalization may remove or trim
content.

Raw unit IDs and indexes are deterministic and continuous in valid
`ExtractionResult`.

`CleanDocumentUnit.clean_unit_id` must be stable by raw lineage:

```python
build_clean_unit_id(document_id, raw_unit.unit_index)
```

`CleanDocumentUnit.clean_unit_index` must be continuous by emitted clean output
order.

## Proposed Implementation Module

Add:

```text
backend/app/rag/cleaning/rule_based_cleaner.py
```

Primary class:

```python
class RuleBasedDocumentCleaner:
    cleaner_name = "rule_based_document_cleaner"
    cleaner_version = "0.1.0"

    def __init__(
        self,
        *,
        policy: CleaningPolicy | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        ...

    def clean(self, input_data: CleaningInput) -> CleaningResult:
        ...
```

Add a policy dataclass in the same module or `policy.py`:

```text
max_input_units
max_input_characters
max_output_units
max_output_characters
```

Recommended default policy for implementation:

```text
max_input_units = 50_000
max_input_characters = 20_000_000
max_output_units = 50_000
max_output_characters = 20_000_000
```

Before implementation, review these defaults against current Phase 2 limits.
HTML extraction currently emits at most 10,000 units and 5,000,000 extracted
characters by default, so cleaner defaults can be higher without changing Phase
2 behavior.

## Cleaned Timestamp

The cleaner must call `clock()` exactly once per cleaning run.

All emitted `CleanDocumentUnit` objects in a single successful
`CleaningResult` must use the same `cleaned_at`.

Tests should inject:

```python
fixed_time = datetime(2026, 6, 13, tzinfo=timezone.utc)
cleaner = RuleBasedDocumentCleaner(clock=lambda: fixed_time)
```

`CleaningService` must not create `cleaned_at` later.

## Construction Algorithm

High-level algorithm:

```text
1. Validate CleaningInput.
2. Enforce input resource limits before processing.
3. Create one run timestamp.
4. Iterate raw units in input order.
5. Normalize content according to content type.
6. If normalized content is blank:
   - append DroppedUnit with reason empty_after_normalization
   - do not emit CleanDocumentUnit
7. Otherwise:
   - assign clean_unit_index = len(output_units)
   - assign clean_unit_id from raw unit_index
   - copy source/document/page/section/heading/content_type metadata
   - preserve raw parser metadata
   - add cleaning metadata except applied rule list
   - set transformations from normalization result
   - set cleaned_at to run timestamp
8. Enforce output resource limits.
9. If no output units, raise CleaningNoContentError.
10. Build CleaningStats.
11. Build and return CleaningResult.
```

## Metadata Policy

Clean units should preserve useful raw metadata:

```python
extra_metadata = {
    **raw.extra_metadata,
    "cleaning": {
        "cleaner": cleaner_name,
        "cleaner_version": cleaner_version,
        "modified": normalized_content != raw.content,
    },
}
```

Do not store:

```text
extra_metadata["cleaning"]["applied_rules"]
```

`transformations` is the source of truth for rule codes.

If raw metadata already contains key `cleaning`, the cleaner must prevent caller
metadata from overwriting service-owned cleaning provenance. Recommended:

* raise `CleaningInputError`, or
* move old value to a namespaced safe field only if explicitly approved.

Prefer raising in Phase 3.3 for strictness.

## Dropped Unit Audit

For blank-after-normalization:

```text
reason_code = empty_after_normalization
message = "Unit became empty after normalization."
original_content_hash = raw.content_hash
source_type = raw.source_type
unit_index = raw.unit_index
page_start/page_end = raw page range
section = raw.section
content_type = raw.content_type
extra_metadata = selected safe metadata
```

Safe metadata should include:

```text
block_type
block_index
page_number
page_block_index
document_block_index
html_tag
serialization_format
```

Do not include:

* full raw content
* `content_bytes`
* secrets
* URL query tokens beyond what Phase 2 already preserved safely

## Stats Policy

`modified_unit_count` means emitted clean units where:

```text
clean.content != raw.content
```

`unchanged_unit_count` means emitted clean units where:

```text
clean.content == raw.content
```

`characters_before` is the sum of raw unit `character_count`.

`characters_after` is the sum of emitted clean unit `character_count`.

`total_input_units` equals input units length.

`total_output_units` equals emitted clean units length.

`dropped_unit_count` equals dropped unit records length.

`warning_count` equals warning records length.

Potential `stats.extra_metadata` counters:

```text
empty_after_normalization_count
normalization_warning_count
modified_character_delta
```

Do not put full content in stats.

## Resource Limit Behavior

If a limit is exceeded:

* raise `CleaningLimitError`
* do not return partial `CleaningResult`
* include safe details:
  * source_id
  * document_id
  * source_type
  * actual count
  * configured limit

Input limits should be checked before work where possible.

Output limits should be checked before returning.

## Warnings

Phase 3.3 may surface normalization warnings created by Phase 3.2 helpers, such
as:

```text
replacement_character_detected
possible_mojibake
suspicious_control_characters_removed
unknown_block_type_fallback
```

All public `CleaningWarning.stage` values must be:

```text
ProcessingStage.cleaning
```

Warnings must not contain full document content.

## Tests To Add

Add:

```text
backend/tests/test_rule_based_cleaner_construction.py
```

Test categories:

* valid single raw unit produces one clean unit
* multiple raw units preserve relative order
* dropped middle raw unit keeps stable clean IDs and continuous clean indexes
* clean ID generated from `raw.unit_index`
* clean ID generation does not parse raw ID string
* all clean units share one injected `cleaned_at`
* cleaned timestamp is timezone-aware
* blank-after-normalization creates `DroppedUnit`
* all blank results raise `CleaningNoContentError`
* dropped records omit full content
* raw metadata preserved
* cleaner-owned `cleaning` metadata added
* caller/raw `cleaning` metadata conflict rejected
* stats equations hold
* input resource limit failure
* output resource limit failure
* no partial success on limit failure
* warnings use `ProcessingStage.cleaning`
* deterministic stable fields across repeated runs with fixed clock

## Verification

Run focused tests:

```text
python -m pytest tests/test_rule_based_cleaner_construction.py
```

Run related tests:

```text
python -m pytest tests/test_cleaning_schema.py tests/test_cleaning_normalization.py tests/test_document_schema.py tests/test_extraction_service.py
```

Run full backend regression:

```text
python -m pytest
```

## Acceptance Criteria

Phase 3.3 is complete when:

* `RuleBasedDocumentCleaner` can build a valid `CleaningResult`.
* One raw unit produces zero or one clean unit.
* Blank-after-normalization units are audited and dropped.
* Clean IDs are stable by raw lineage.
* Clean indexes are continuous by output order.
* Stats satisfy all contract equations.
* Resource limits fail without partial results.
* All emitted clean units in one result share one timestamp.
* No source-aware noise filtering or deduplication is implemented.
* No dependencies are added.

## Deferred To Later Sub-Phases

* HTML UI and reading-time filtering: Phase 3.4.
* PDF page-number warning/drop logic: Phase 3.4.
* Exact deduplication: Phase 3.5.
* Service-level `ExtractionResult -> CleaningResult`: Phase 3.6.

