# Phase 3.1 - Cleaning Core Contracts

Status: Planned.

## Purpose

Create the strict contracts needed for Phase 3 cleaning without implementing
real cleaning rules yet.

This sub-phase prepares:

* Updated `CleanDocumentUnit` contract.
* Cleaning input/result schemas.
* Cleaning warning, dropped-unit, and stats schemas.
* Cleaning runtime error taxonomy.
* Cleaner protocol.
* Deterministic clean ID helper.
* Contract and invariant tests.

No normalization, filtering, deduplication, service orchestration, API routes,
database persistence, chunking, embedding, indexing, retrieval, or generation is
implemented in this sub-phase.

## Context Read

Required documents inspected:

* `backend/AGENTS.md`
* `.agents/architecture.md`
* `.agents/tasks/phase_2_extraction_and_parsing/phase_2_source_extraction_overview.md`
* `.agents/tasks/phase_3_cleaning_and_normalization/phase_3_overview.md`

Requested but missing:

* `.agents/tasks/phase_3_cleaning_and_normalization/phase_3_cleaning_and_normalization_overview.md`

Resolution for planning:

* Use the actual existing overview file: `phase_3_overview.md`.
* Do not rename or duplicate the overview unless explicitly requested.

Code and tests inspected:

* `backend/app/schemas/common.py`
* `backend/app/schemas/source.py`
* `backend/app/schemas/document.py`
* `backend/app/schemas/extraction.py`
* `backend/app/providers/extraction/`
* `backend/app/providers/fetching/`
* `backend/app/services/extraction.py`
* `backend/app/core/errors.py`
* `backend/tests/test_document_schema.py`
* `backend/tests/test_extraction_schema.py`
* `backend/tests/test_extraction_errors.py`
* `backend/tests/test_extraction_ids.py`
* `backend/tests/test_extraction_interface.py`
* `backend/tests/test_extraction_service.py`
* DOCX/PDF/HTML extractor tests
* URL fetcher tests
* source/retrieval/generation schema tests
* `backend/pyproject.toml`

## Current Implementation Facts

`PipelineSchema` forbids unknown fields globally.

`ProcessingStage.cleaning` already exists in `backend/app/schemas/source.py`.
Do not add it again.

`RawDocumentUnit` currently has:

```text
raw_unit_id
unit_index
extracted_at
```

`ExtractionResult` already validates:

* non-empty units
* unique `raw_unit_id`
* unique `unit_index`
* continuous ordered `unit_index`
* unit/result lineage match
* stats count match

Current `CleanDocumentUnit` has:

```text
clean_unit_id
raw_unit_id
transformations
original_character_count
removed_character_count
cleaned_at
```

It does not yet have:

```text
clean_unit_index
```

Current document schema tests expect `original_character_count` and
`removed_character_count`. These tests must be updated when the contract changes.

No cleaning schemas, cleaning protocol, cleaning errors, cleaning ID helper,
cleaner implementation, or cleaning service currently exist.

## Contract Decisions Already Made

`CleanDocumentUnit` must add:

```text
clean_unit_index
```

`clean_unit_index` belongs only to `CleanDocumentUnit`. Do not add it to:

* `DocumentUnitBase`
* `RawDocumentUnit`
* `DocumentChunk`

`CleanDocumentUnit` must remove:

```text
original_character_count
removed_character_count
```

`clean_unit_id` must be generated from `RawDocumentUnit.unit_index`, not output
position and not by parsing `raw_unit_id`:

```python
clean_unit_id = f"clean:{document_id}:{raw_unit.unit_index:06d}"
```

`transformations` remains first-class and is the source of truth for stable
machine-readable rule codes applied to each clean unit. Do not duplicate these
codes in `extra_metadata["cleaning"]["applied_rules"]`.

`cleaned_at` remains first-class. The cleaner implementation, not
`CleaningService`, creates one UTC-aware timestamp for all clean units emitted in
one cleaning run.

## Contract Conflicts And Resolutions

### Conflict: overview filename mismatch

The user requested `phase_3_cleaning_and_normalization_overview.md`, but the repo
contains `phase_3_overview.md`.

Resolution:

* Continue planning from `phase_3_overview.md`.
* Mention this in final reporting.
* Do not create or rename the overview file in this task.

### Conflict: existing `CleanDocumentUnit` metrics

Current code requires `original_character_count` and may derive
`removed_character_count`. The Phase 3 decision removes both.

Impact:

* `backend/app/schemas/document.py` must change in Phase 3.1.
* Existing document schema tests must be updated.
* Any future code constructing `CleanDocumentUnit` must use aggregate stats
  instead of per-unit removed-character fields.

Resolution:

* Remove both fields and their validator.
* Add `clean_unit_index`.
* Keep schema-computed `character_count`, `word_count`, and `content_hash`.

### Contract caveat: result-level invariants need raw context

Some overview invariants require knowledge of original `RawDocumentUnit` inputs:

* every input raw unit is emitted or dropped
* `clean_unit_id` derives from the referenced raw unit's `unit_index`
* clean-unit relative order follows raw-unit relative order

`CleaningResult` alone does not have the full raw input unless it stores extra
raw context. Adding raw context to `CleaningResult` would make the public
contract heavier.

Recommended resolution:

* `CleaningResult` schema enforces self-contained invariants:
  * non-empty units
  * unique clean IDs
  * continuous ordered clean indexes
  * emitted/dropped raw ID disjointness
  * lineage consistency
  * stats count consistency
  * one `cleaned_at` per result
* Cleaner construction tests in Phase 3.3 enforce raw-input invariants using
  `CleaningInput` plus `CleaningResult`.
* Do not add `raw_unit_index` or full raw input snapshots to `CleaningResult`
  unless later implementation proves schema-only validation is necessary.

## Proposed Module Layout

Use the internal RAG pipeline boundary for cleaning, because cleaning is a
deterministic internal transformation rather than an external provider.

Planned files:

```text
backend/app/schemas/cleaning.py
backend/app/rag/cleaning/__init__.py
backend/app/rag/cleaning/interface.py
backend/app/rag/cleaning/errors.py
backend/app/rag/cleaning/ids.py
```

Rationale:

* `schemas/` continues to own Pydantic contracts.
* `rag/cleaning/` owns pipeline-specific cleaner protocol, IDs, and runtime
  errors.
* `services/` will orchestrate the cleaner later in Phase 3.6.
* No external dependency is wrapped, so a `providers/cleaning/` implementation is
  not necessary.

If the project later standardizes all injectable interfaces under
`providers/`, move the protocol then; do not do that preemptively.

## Schemas To Add

Create `backend/app/schemas/cleaning.py`.

### CleaningInput

Fields:

```text
source_id: NonEmptyStr
document_id: NonEmptyStr
source_type: SourceType
units: list[RawDocumentUnit]
cleaner_config: dict[str, object]
extra_metadata: dict[str, object]
```

Rules:

* units must be non-empty
* unit list order must match `RawDocumentUnit.unit_index`
* unit indexes must be continuous from zero
* unit raw IDs must be unique
* every unit must match input `source_id`, `document_id`, and `source_type`
* unknown fields rejected through `PipelineSchema`

### CleaningWarning

Fields:

```text
warning_code: NonEmptyStr
message: NonEmptyStr
stage: ProcessingStage
raw_unit_id: NonEmptyStr | None
clean_unit_index: int | None
extra_metadata: dict[str, object]
```

Rules:

* `stage` must be `ProcessingStage.cleaning`
* indexes must be non-negative when present
* message and metadata must not include full raw content

### DroppedUnit

Fields:

```text
raw_unit_id: NonEmptyStr
reason_code: NonEmptyStr
message: NonEmptyStr
original_content_hash: NonEmptyStr
source_type: SourceType
unit_index: int
page_start: int | None
page_end: int | None
section: str | None
content_type: DocumentContentType
extra_metadata: dict[str, object]
```

Notes:

* Do not include full original content.
* Store only safe metadata needed to audit the drop.
* `unit_index` is required because every valid dropped record represents one
  concrete `RawDocumentUnit`, and every valid `RawDocumentUnit` has
  `unit_index >= 0`.
* `unit_index` must be the original raw-unit position, not output clean-unit
  position.
* Page range validation should match `DocumentUnitBase` behavior.

### CleaningStats

Fields:

```text
total_input_units: int
total_output_units: int
dropped_unit_count: int
modified_unit_count: int
unchanged_unit_count: int
warning_count: int
characters_before: int
characters_after: int
extra_metadata: dict[str, object]
```

Rules:

* counts are non-negative
* `total_input_units` must be at least 1

### CleaningResult

Fields:

```text
source_id: NonEmptyStr
document_id: NonEmptyStr
source_type: SourceType
cleaner_name: NonEmptyStr
cleaner_version: NonEmptyStr
units: list[CleanDocumentUnit]
dropped_units: list[DroppedUnit]
warnings: list[CleaningWarning]
stats: CleaningStats
```

Rules:

* units must be non-empty on success
* clean IDs unique
* clean indexes unique, continuous, ordered from zero
* result lineages match emitted clean units
* warning count matches
* dropped count matches
* input/output/drop equation matches
* modified/unchanged equation matches
* emitted and dropped raw IDs are disjoint
* dropped unit indexes are unique and ordered by raw-unit position
* all clean units share one `cleaned_at`
* warnings must use `ProcessingStage.cleaning`

## Document Schema Changes

Update `backend/app/schemas/document.py`:

```python
class CleanDocumentUnit(DocumentUnitBase):
    clean_unit_id: NonEmptyStr
    clean_unit_index: int = Field(ge=0)
    raw_unit_id: NonEmptyStr
    transformations: list[NonEmptyStr] = Field(default_factory=list)
    cleaned_at: datetime
```

Remove:

```python
original_character_count
removed_character_count
validate_cleaning_metrics()
```

Add validation for `cleaned_at` timezone only if the project accepts a schema
validator here. Recommended:

* reject naive datetimes
* require timezone-aware datetime
* prefer UTC in tests and implementation

## Runtime Errors To Add

Create `backend/app/rag/cleaning/errors.py` with extraction-like shape:

```text
CleaningError
CleaningInputError
CleaningNoContentError
CleaningLimitError
CleaningInvariantError
```

Each error should expose:

```text
error_code
message
retryable
details
```

Stable error codes:

```text
cleaning_error
cleaning_input_error
cleaning_no_content
cleaning_limit_exceeded
cleaning_invariant_failed
```

Errors must not include full raw content, binary data, secrets, or raw document
text in details.

## ID Helper To Add

Create `backend/app/rag/cleaning/ids.py`.

Function:

```python
def build_clean_unit_id(document_id: str, raw_unit_index: int) -> str:
    ...
```

Rules:

* strip `document_id`
* reject blank `document_id`
* reject negative `raw_unit_index`
* return `clean:{document_id}:{raw_unit_index:06d}`
* do not accept or parse `raw_unit_id`

## Cleaner Protocol To Add

Create `backend/app/rag/cleaning/interface.py`.

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class ContentCleaner(Protocol):
    def clean(self, input_data: CleaningInput) -> CleaningResult:
        ...
```

No implementation in Phase 3.1.

## Tests To Add Or Update

Update:

```text
backend/tests/test_document_schema.py
```

Add:

```text
backend/tests/test_cleaning_schema.py
backend/tests/test_cleaning_errors.py
backend/tests/test_cleaning_ids.py
backend/tests/test_cleaning_interface.py
```

Test categories:

* valid `CleanDocumentUnit` with `clean_unit_index`
* rejected missing/negative `clean_unit_index`
* rejected old fields as unknown input
* `transformations` rejects blank entries
* default list isolation for transformations
* timezone-aware `cleaned_at` behavior if validator is added
* valid `CleaningInput`
* input rejects empty units
* input rejects duplicate/non-continuous raw unit indexes
* input rejects lineage mismatch
* valid `CleaningWarning`
* warning rejects non-cleaning stage
* valid `DroppedUnit`
* dropped unit requires `unit_index`
* dropped unit rejects negative `unit_index`
* dropped unit rejects invalid page range
* valid `CleaningResult`
* result rejects duplicate clean IDs
* result rejects duplicate/non-continuous clean indexes
* result rejects list order mismatch
* result rejects stats mismatch
* result rejects emitted/dropped raw ID overlap
* result rejects duplicate dropped unit indexes
* result rejects dropped units ordered differently from raw-unit position
* result rejects multiple `cleaned_at` values
* ID helper format/rejection/determinism
* protocol works with fake cleaner
* error classes expose stable error codes

## Verification

Run focused tests:

```text
python -m pytest tests/test_document_schema.py tests/test_cleaning_schema.py tests/test_cleaning_errors.py tests/test_cleaning_ids.py tests/test_cleaning_interface.py
```

Run related regression:

```text
python -m pytest tests/test_extraction_schema.py tests/test_extraction_service.py
```

Run full backend regression:

```text
python -m pytest
```

## Acceptance Criteria

Phase 3.1 is complete when:

* `CleanDocumentUnit` contract matches Phase 3 decisions.
* Cleaning schemas exist and reject unknown fields.
* Cleaning result invariants are explicit and tested.
* Cleaner protocol exists and is runtime-checkable.
* Cleaning runtime errors exist and expose stable safe diagnostics.
* Clean ID helper exists and never parses raw IDs.
* `ProcessingStage.cleaning` is verified as already present.
* No real cleaning rules are implemented.
* No dependencies are added.
* Focused, related, and full backend tests pass or failures are explained.

## Deferred To Later Sub-Phases

* Actual normalization rules: Phase 3.2.
* Clean-unit construction from raw units: Phase 3.3.
* HTML/PDF source-aware filtering: Phase 3.4.
* Deduplication: Phase 3.5.
* `CleaningService`: Phase 3.6.
* Documentation/completion report: Phase 3.7.
