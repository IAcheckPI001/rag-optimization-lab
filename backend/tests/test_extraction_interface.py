from datetime import datetime

import app.providers.extraction.interface as extraction_interface
from app.providers.extraction.interface import ContentExtractor
from app.schemas.document import DocumentContentType, RawDocumentUnit
from app.schemas.extraction import ExtractionInput, ExtractionResult, ExtractionStats
from app.schemas.source import SourceType


class FakeExtractor:
    def extract(self, input_data: ExtractionInput) -> ExtractionResult:
        unit = RawDocumentUnit(
            document_id=input_data.document_id,
            source_id=input_data.source_id,
            source_type=input_data.source_type,
            source_uri=input_data.source_uri,
            content="Extracted content.",
            page_start=None,
            page_end=None,
            section=None,
            heading_path=[],
            content_type=DocumentContentType.paragraph,
            extra_metadata={"extractor": "fake"},
            raw_unit_id=f"raw:{input_data.document_id}:000000",
            unit_index=0,
            extracted_at=datetime(2026, 6, 8, 9, 0),
        )
        return ExtractionResult(
            source_id=input_data.source_id,
            document_id=input_data.document_id,
            source_type=input_data.source_type,
            extractor_name="fake",
            extractor_version="0.1.0",
            units=[unit],
            warnings=[],
            stats=ExtractionStats(total_units=1, warning_count=0),
        )


def run_extractor(extractor: ContentExtractor) -> ExtractionResult:
    return extractor.extract(
        ExtractionInput(
            source_id="src_001",
            document_id="doc_001",
            source_type=SourceType.pdf,
            content_bytes=b"pdf bytes",
        )
    )


def test_old_extraction_interfaces_are_removed() -> None:
    assert not hasattr(extraction_interface, "PDFExtractor")
    assert not hasattr(extraction_interface, "DocxExtractor")
    assert not hasattr(extraction_interface, "WebExtractor")


def test_content_extractor_works_with_fake_implementation() -> None:
    result = run_extractor(FakeExtractor())

    assert result.extractor_name == "fake"
    assert result.units[0].content == "Extracted content."
    assert result.units[0].unit_index == 0
