from datetime import datetime, timezone

from app.rag.cleaning.interface import ContentCleaner
from app.schemas.cleaning import CleaningInput, CleaningResult, CleaningStats
from app.schemas.document import CleanDocumentUnit, DocumentContentType, RawDocumentUnit
from app.schemas.source import SourceType


def raw_unit() -> RawDocumentUnit:
    return RawDocumentUnit.model_validate(
        {
            "document_id": "document-001",
            "source_id": "source-001",
            "source_type": SourceType.pdf,
            "content": "Raw content",
            "content_type": DocumentContentType.paragraph,
            "raw_unit_id": "raw:document-001:000000",
            "unit_index": 0,
            "extracted_at": datetime(2026, 6, 12, tzinfo=timezone.utc),
        }
    )


def clean_unit() -> CleanDocumentUnit:
    return CleanDocumentUnit.model_validate(
        {
            "document_id": "document-001",
            "source_id": "source-001",
            "source_type": SourceType.pdf,
            "content": "Clean content",
            "content_type": DocumentContentType.paragraph,
            "clean_unit_id": "clean:document-001:000000",
            "clean_unit_index": 0,
            "raw_unit_id": "raw:document-001:000000",
            "transformations": ["unicode_nfc"],
            "cleaned_at": datetime(2026, 6, 13, tzinfo=timezone.utc),
        }
    )


def cleaning_input() -> CleaningInput:
    return CleaningInput.model_validate(
        {
            "source_id": "source-001",
            "document_id": "document-001",
            "source_type": SourceType.pdf,
            "units": [raw_unit()],
        }
    )


class FakeCleaner:
    def clean(self, input_data: CleaningInput) -> CleaningResult:
        return CleaningResult.model_validate(
            {
                "source_id": input_data.source_id,
                "document_id": input_data.document_id,
                "source_type": input_data.source_type,
                "cleaner_name": "fake-cleaner",
                "cleaner_version": "0.1.0",
                "units": [clean_unit()],
                "dropped_units": [],
                "warnings": [],
                "stats": CleaningStats.model_validate(
                    {
                        "total_input_units": 1,
                        "total_output_units": 1,
                        "dropped_unit_count": 0,
                        "modified_unit_count": 1,
                        "unchanged_unit_count": 0,
                        "warning_count": 0,
                        "characters_before": 11,
                        "characters_after": 13,
                    }
                ),
            }
        )


def test_content_cleaner_protocol_accepts_fake_cleaner() -> None:
    cleaner = FakeCleaner()

    assert isinstance(cleaner, ContentCleaner)


def test_content_cleaner_protocol_returns_cleaning_result() -> None:
    cleaner: ContentCleaner = FakeCleaner()

    result = cleaner.clean(cleaning_input())

    assert result.cleaner_name == "fake-cleaner"
    assert result.units[0].clean_unit_index == 0
