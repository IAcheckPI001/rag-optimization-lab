from typing import Protocol, runtime_checkable

from app.schemas.extraction import ExtractionInput, ExtractionResult


@runtime_checkable
class ContentExtractor(Protocol):
    def extract(self, input_data: ExtractionInput) -> ExtractionResult:
        ...
