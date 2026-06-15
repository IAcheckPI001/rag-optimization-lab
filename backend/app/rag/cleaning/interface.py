from typing import Protocol, runtime_checkable

from app.schemas.cleaning import CleaningInput, CleaningResult


@runtime_checkable
class ContentCleaner(Protocol):
    def clean(self, input_data: CleaningInput) -> CleaningResult:
        """Return cleaned document units for a validated cleaning input."""
