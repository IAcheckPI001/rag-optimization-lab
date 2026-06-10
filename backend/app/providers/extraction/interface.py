from typing import Protocol

from app.schemas.extraction import ExtractionInput, ExtractionResult


class ContentExtractor(Protocol):
    def extract(self, input_data: ExtractionInput) -> ExtractionResult:
        ...
