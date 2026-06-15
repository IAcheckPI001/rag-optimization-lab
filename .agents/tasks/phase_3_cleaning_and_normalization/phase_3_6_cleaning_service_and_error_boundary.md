# Phase 3.6 - Cleaning Service And Error Boundary

Status: Planned.

Depends on:

* Phase 3.5 completed cleaner behavior.

## Purpose

Add application service orchestration:

```text
ExtractionResult -> CleaningService -> CleaningResult
```

The service should be thin but useful:

* accept `ExtractionResult`
* build `CleaningInput`
* inject and call `ContentCleaner`
* map known cleaning runtime errors to `SourceError`
* preserve exception chaining
* remain independent of FastAPI, repositories, persistence, and routes

Do not implement API routes, background jobs, database persistence, chunking,
embedding, indexing, retrieval, or generation.

## Current Implementation Pattern To Mirror

`backend/app/services/extraction.py` currently:

* accepts primitive inputs for extraction workflows
* builds `ExtractionInput`
* calls injected extractor/fetcher interfaces
* maps provider errors to `SourceError`
* wraps errors in `ExtractionServiceError`
* preserves `__cause__`
* rejects reserved metadata keys
* does not depend on FastAPI or persistence

Phase 3.6 should mirror this shape, not invent a new service style.

## Proposed Service Module

Add:

```text
backend/app/services/cleaning.py
```

Classes/functions:

```text
CleaningService
CleaningServiceInputError
CleaningServiceError
map_to_source_error
```

Constructor:

```python
class CleaningService:
    def __init__(self, *, cleaner: ContentCleaner) -> None:
        self.cleaner = cleaner
```

Entry point:

```python
def clean_extraction_result(
    self,
    extraction_result: ExtractionResult,
    *,
    cleaner_config: dict[str, object] | None = None,
    extra_metadata: dict[str, object] | None = None,
) -> CleaningResult:
    ...
```

No bytes, URLs, `UploadFile`, parser objects, or database records should be
accepted here.

## Metadata Policy

Reserve service-owned extra metadata keys.

Recommended reserved keys:

```text
service
cleaning
```

Potential service metadata added to `CleaningInput.extra_metadata`:

```text
source_extractor_name
source_extractor_version
source_warning_count
```

Do not copy full extracted content into metadata.

Do not mutate the `ExtractionResult`.

## Error Mapping

Map cleaning errors to `SourceError` with:

```text
failed_stage = ProcessingStage.cleaning
```

Suggested mappings:

```text
CleaningInputError      -> cleaning_input_error
CleaningNoContentError  -> cleaning_no_content
CleaningLimitError      -> cleaning_limit_exceeded
CleaningInvariantError  -> cleaning_invariant_failed
CleaningError           -> cleaning_error
```

`retryable` should come from the cleaning error object and default to false.

Unexpected implementation bugs should not be swallowed by broad exception
catches.

`CleaningServiceError` should carry:

```text
source_error: SourceError
```

and preserve exception chaining:

```python
raise self._service_error(exc) from exc
```

## Input Validation

The service should reject:

* empty or invalid `ExtractionResult` through existing schema behavior
* reserved `extra_metadata` keys
* non-mapping metadata values if accepted by caller interface

The service should rely on `CleaningInput` for lineage and unit-order
validation.

## Tests To Add

Add:

```text
backend/tests/test_cleaning_service.py
```

Test categories:

* service builds `CleaningInput` from `ExtractionResult`.
* service passes cleaner_config.
* service passes safe extra_metadata.
* service rejects reserved metadata keys.
* service returns cleaner result.
* service does not mutate extraction result.
* fake cleaner protocol works.
* `CleaningInputError` maps to `ProcessingStage.cleaning`.
* `CleaningNoContentError` maps to `ProcessingStage.cleaning`.
* `CleaningLimitError` maps to `ProcessingStage.cleaning`.
* `CleaningInvariantError` maps to `ProcessingStage.cleaning`.
* service error preserves `__cause__`.
* real `RuleBasedDocumentCleaner` works with DOCX/PDF/HTML extraction service
  outputs using local in-memory fixtures and fake URL fetcher.
* tests do not call real websites.

## Integration Test Shape

Use existing Phase 2 service helpers as a model:

```text
DocxExtractor -> ExtractionService.extract_bytes -> CleaningService
PdfExtractor  -> ExtractionService.extract_bytes -> CleaningService
HtmlExtractor -> ExtractionService.extract_url   -> CleaningService
```

For URL path, use fake URL fetcher as current tests do.

Assertions:

* cleaning result lineages match extraction result
* clean unit indexes continuous
* clean IDs generated from raw indexes
* all clean units share one cleaned_at
* raw parser metadata preserved
* no external network calls

## Verification

Run focused tests:

```text
python -m pytest tests/test_cleaning_service.py
```

Run related tests:

```text
python -m pytest tests/test_extraction_service.py tests/test_rule_based_cleaner_construction.py tests/test_cleaning_schema.py
```

Run full backend regression:

```text
python -m pytest
```

## Acceptance Criteria

Phase 3.6 is complete when:

* `CleaningService` orchestrates `ExtractionResult -> CleaningResult`.
* Service remains independent of FastAPI and persistence.
* Service depends on `ContentCleaner`, not concrete cleaner internals.
* Known cleaning errors map to `SourceError` with `failed_stage=cleaning`.
* Exception chaining is preserved.
* No raw content leaks into errors or metadata.
* Integration tests cover DOCX, PDF, and URL/HTML paths without external calls.
* No API routes, database schema, chunking, embedding, indexing, retrieval, or
  generation are added.

## Deferred

* API endpoint wiring, if requested, belongs to a later API phase.
* Persistence and retrieval logs are later MVP phases.
* Background jobs are out of scope.

