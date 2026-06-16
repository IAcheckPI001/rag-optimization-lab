# Phase 3.3 - Clean Unit Construction

Status: Completed.

Depends on:

* Phase 3.1 cleaning contracts.
* Phase 3.2 deterministic normalization helpers.

## Completion Notes

* Added `RuleBasedDocumentCleaner` and `CleaningPolicy` in
  `backend/app/rag/cleaning/rule_based_cleaner.py`.
* Implemented raw-to-clean candidate construction with `_DropDecision | None`
  so candidate state cannot represent contradictory drop states.
* Implemented blank-after-normalization dropping with one `DroppedUnit` per
  dropped raw unit.
* Implemented deterministic clean IDs from `RawDocumentUnit.unit_index` and
  continuous `clean_unit_index` from emitted output order.
* Implemented safe dropped-unit audit records using `raw.content_hash` and a
  metadata allowlist.
* Implemented strict top-level raw `extra_metadata["cleaning"]` conflict
  rejection while allowing nested source metadata keys named `cleaning`.
* Implemented policy precedence:
  defaults -> constructor policy -> allowlisted `cleaner_config` overrides.
* Implemented strict `cleaner_config` validation, including bool rejection.
* Implemented clock behavior: successful runs call `clock()` exactly once,
  naive datetimes raise `CleaningInvariantError`, aware non-UTC datetimes are
  normalized to UTC, and input/config/limit/all-dropped failures do not call
  `clock()`.
* Implemented public `CleaningWarning` finalization from internal normalization
  warnings, attaching final clean indexes for emitted units and `None` for
  dropped units.
* Implemented cleaning statistics and all schema equations.
* Added focused construction tests in
  `backend/tests/test_rule_based_cleaner_construction.py`.
* Verification completed with full backend regression:
  `411 passed, 2 warnings`.

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

Policy precedence must be explicit:

```text
CleaningPolicy defaults
-> constructor policy
-> CleaningInput.cleaner_config allowlisted per-run overrides
```

Allowed `cleaner_config` override keys in Phase 3.3:

```text
max_input_units
max_input_characters
max_output_units
max_output_characters
```

Unknown `cleaner_config` keys must raise `CleaningInputError`.

Allowed override values must be integers greater than or equal to `1`.

Reject these override values:

```python
True
False
1.5
"100"
None
0
-1
```

Because `bool` is a subclass of `int` in Python, validation must not rely only
on:

```python
isinstance(value, int)
```

Use an explicit bool check:

```python
if isinstance(value, bool) or not isinstance(value, int):
    raise CleaningInputError(...)
```

Do not allow `cleaner_config` to change normalization behavior in Phase 3.3.
The following remain out of scope:

```text
trim_code_outer_blank_lines
drop_pdf_page_numbers
html_noise_rules
deduplicate
```

## Cleaned Timestamp

The cleaner must call `clock()` exactly once per cleaning run.

All emitted `CleanDocumentUnit` objects in a single successful
`CleaningResult` must use the same `cleaned_at`.

Clock behavior:

* successful runs call `clock()` exactly once
* naive datetimes from `clock()` raise `CleaningInvariantError`
* timezone-aware non-UTC datetimes are normalized to UTC before assignment
* input, config, resource-limit, and all-dropped failures do not call `clock()`

To satisfy this, call `clock()` only after:

* input/config validation has passed
* input resource limits have passed
* candidates have been built
* at least one candidate will be emitted

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
2. Resolve effective policy from defaults, constructor policy, and
   allowlisted `cleaner_config` overrides.
3. Reject top-level raw metadata conflicts with service-owned cleaning
   metadata.
4. Enforce input resource limits before processing.
5. Normalize raw units into internal candidates in raw input order.
6. Mark candidates as dropped when normalized content is blank.
7. If no candidates will be emitted, raise CleaningNoContentError without
   creating a successful timestamp.
8. Create one run timestamp.
9. Finalize candidates:
   - assign continuous clean indexes only to emitted units
   - assign clean IDs from raw unit indexes
   - build dropped-unit audit records
   - attach public warnings with final clean indexes where available
10. Enforce output resource limits.
11. Build CleaningStats.
12. Build and return CleaningResult.
```

Use an internal candidate/finalization structure so later Phase 3.4 and 3.5
rules can add source-aware drops or duplicate drops without refactoring clean
index assignment and warning attachment.

Recommended internal shape:

```python
@dataclass(frozen=True)
class _CleanCandidate:
    raw_unit: RawDocumentUnit
    normalized: NormalizedContent
    drop: _DropDecision | None = None


@dataclass(frozen=True)
class _DropDecision:
    reason_code: str
    message: str
```

Avoid candidate shapes with independent nullable fields such as:

```python
should_drop: bool
drop_reason_code: str | None
drop_message: str | None
```

Those can represent contradictory states like `should_drop=True` with no
reason. A single optional `_DropDecision` keeps candidate state coherent:

```text
drop is None        -> emitted candidate
drop is not None    -> dropped candidate with required reason/message
```

Finalization is the only place that assigns:

* `clean_unit_index`
* `clean_unit_id`
* public `CleaningWarning.clean_unit_index`
* output statistics

Warnings from normalization should stay internal on candidates until
finalization. If a candidate is emitted, attach the final clean index to its
warnings. If a candidate is dropped, keep `clean_unit_index=None`.

Do not mutate already-created public warning objects to fill indexes later.

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
metadata from overwriting service-owned cleaning provenance.

Phase 3.3 must reject the conflict with `CleaningInputError`.

The conflict scope is exact:

```python
"cleaning" in raw_unit.extra_metadata
```

This check applies only to the top-level `extra_metadata` of each
`RawDocumentUnit`.

Do not reject nested metadata keys named `cleaning`, for example:

```python
extra_metadata={
    "parser_details": {"cleaning": "literal source field"}
}
```

Do not reject `CleaningInput.extra_metadata["cleaning"]` in Phase 3.3 unless the
cleaner starts merging input-level metadata into per-unit metadata. That concern
belongs to the service/run metadata boundary in a later phase.

No conflict error may include full raw content.

## Blank Unit Rule

Use one helper for blank-after-normalization decisions:

```python
def is_blank_after_normalization(content: str) -> bool:
    return content == "" or all(character.isspace() for character in content)
```

The following must be treated as blank:

```python
""
"   "
"\t\n"
"\u00a0"
"\n\t\u00a0"
```

Do not treat zero-width or Unicode format-only content as blank in Phase 3.3 if
Phase 3.2 has not removed it:

```python
"\u200b"  # zero-width space, category Cf
"\ufeff"  # BOM / zero-width no-break space, category Cf
```

Those values may be addressed by a future reviewed Unicode format-character
policy, but Phase 3.3 must not silently drop them.

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

Dropped audit metadata must copy only this allowlist. It must not copy the full
raw `extra_metadata` dictionary.

`original_content_hash` must always be:

```python
raw.content_hash
```

Do not compute the dropped hash from normalized blank content.

Do not include:

* full raw content
* `content_bytes`
* secrets
* URL query tokens beyond what Phase 2 already preserved safely

If every input unit is dropped after normalization:

```text
all units normalize to blank
-> build one DroppedUnit per raw unit internally
-> do not return partial CleaningResult
-> raise CleaningNoContentError
```

`CleaningNoContentError.details` may include safe aggregate counts such as:

```text
source_id
document_id
source_type
total_input_units
dropped_unit_count
reason_code = empty_after_normalization
```

Do not include full raw content or dropped-unit records in the exception unless
a later persistence/audit requirement explicitly asks for it.

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

Stats must satisfy:

```text
total_input_units
= total_output_units + dropped_unit_count
```

```text
modified_unit_count + unchanged_unit_count
= total_output_units
```

```text
warning_count = len(warnings)
```

`characters_before` counts all raw units, including dropped units.

`characters_after` counts emitted clean units only.

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

Warning attachment must happen during finalization:

* emitted candidate warnings get `raw_unit_id` and final `clean_unit_index`
* dropped candidate warnings get `raw_unit_id` and `clean_unit_index=None`
* run-level warnings, if any are introduced later, may keep both unit fields
  unset

Phase 3.3 should not emit `possible_mojibake` unless Phase 3.2 actually returns
that internal warning. Current Phase 3.2 only emits reviewed normalization
warnings.

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
* blank helper treats empty string, ASCII spaces, tabs, newlines, NBSP, and
  mixed whitespace as blank
* blank helper does not treat zero-width or Unicode `Cf`-only content as blank
* all blank results raise `CleaningNoContentError`
* all blank results internally build one dropped record per raw unit but do not
  return a partial `CleaningResult`
* dropped records omit full content
* raw metadata preserved
* cleaner-owned `cleaning` metadata added
* top-level raw `extra_metadata["cleaning"]` conflict rejected
* nested raw metadata key named `cleaning` is not rejected
* allowed `cleaner_config` resource limit overrides apply per run
* unknown `cleaner_config` keys are rejected
* invalid `cleaner_config` limit values are rejected
* bool `cleaner_config` limit values are rejected even though bool subclasses int
* `cleaner_config` rejects `True`, `False`, `1.5`, `"100"`, `None`, `0`, and
  `-1`
* stats equations hold
* `characters_before` counts all raw units
* `characters_after` counts only emitted clean units
* input resource limit failure
* output resource limit failure
* no partial success on limit failure
* successful run calls `clock()` exactly once
* naive `clock()` result raises `CleaningInvariantError`
* aware non-UTC `clock()` result is normalized to UTC
* input/config/limit/all-dropped failures do not call `clock()`
* warnings use `ProcessingStage.cleaning`
* emitted-unit warnings receive final `clean_unit_index`
* dropped-unit warnings keep `clean_unit_index=None`
* dropped audit uses `original_content_hash = raw.content_hash`
* dropped audit copies only safe metadata allowlist
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
* Blank detection follows the shared helper semantics.
* Top-level service-owned cleaning metadata conflicts are rejected.
* Policy precedence and `cleaner_config` override validation are explicit.
* Candidate finalization owns clean indexes and warning attachment.
* No source-aware noise filtering or deduplication is implemented.
* No dependencies are added.

## Deferred To Later Sub-Phases

* HTML UI and reading-time filtering: Phase 3.4.
* PDF page-number warning/drop logic: Phase 3.4.
* Exact deduplication: Phase 3.5.
* Service-level `ExtractionResult -> CleaningResult`: Phase 3.6.
