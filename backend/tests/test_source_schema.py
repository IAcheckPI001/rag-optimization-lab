from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas.source import (
    DocxSourceMetadata,
    PdfSourceMetadata,
    ProcessingStage,
    SourceDetailResponse,
    SourceError,
    SourceStatus,
    SourceType,
    UrlSourceMetadata,
)


def test_source_detail_accepts_pdf_metadata() -> None:
    source = SourceDetailResponse(
        source_id="src_pdf_001",
        source_type=SourceType.pdf,
        status=SourceStatus.processing,
        display_name="Quarterly Report",
        current_stage=ProcessingStage.extracting,
        input_uri="report.pdf",
        source_uri="storage://sources/src_pdf_001/raw.pdf",
        canonical_uri="document://src_pdf_001",
        created_at=datetime(2026, 6, 6, 9, 30),
        metadata={
            "metadata_type": "pdf",
            "title": "Quarterly Report",
            "original_filename": "report.pdf",
            "checksum_sha256": "abc123",
            "total_pages": 12,
        },
    )

    assert source.source_id == "src_pdf_001"
    assert source.current_stage is ProcessingStage.extracting
    assert isinstance(source.metadata, PdfSourceMetadata)
    assert source.metadata.mime_type == "application/pdf"
    assert source.metadata.total_pages == 12


def test_source_detail_accepts_docx_metadata() -> None:
    source = SourceDetailResponse(
        source_id="src_docx_001",
        source_type=SourceType.docx,
        status=SourceStatus.completed,
        current_stage=ProcessingStage.completed,
        created_at=datetime(2026, 6, 6, 10, 0),
        metadata={
            "metadata_type": "docx",
            "title": "Research Notes",
            "original_filename": "notes.docx",
            "paragraph_count": 20,
            "table_count": 2,
        },
    )

    assert isinstance(source.metadata, DocxSourceMetadata)
    assert source.metadata.original_filename == "notes.docx"
    assert source.metadata.paragraph_count == 20
    assert source.metadata.table_count == 2


def test_source_detail_accepts_url_metadata_and_error() -> None:
    source = SourceDetailResponse(
        source_id="src_url_001",
        source_type=SourceType.url,
        status=SourceStatus.failed,
        current_stage=ProcessingStage.failed,
        input_uri="https://example.com/article",
        canonical_uri="https://example.com/article",
        created_at=datetime(2026, 6, 6, 11, 0),
        error={
            "error_code": "URL_HTTP_403",
            "message": "The URL returned HTTP 403.",
            "failed_stage": "downloading",
        },
        metadata={
            "metadata_type": "url",
            "original_url": "https://example.com/article",
            "final_url": "https://example.com/article",
            "canonical_url": "https://example.com/article",
            "domain": "example.com",
            "site_name": "Example",
            "title": "Example Article",
            "description": "A sample article.",
            "language": "en",
            "author": "Example Author",
            "published_at": datetime(2026, 6, 1, 8, 0),
            "updated_at": datetime(2026, 6, 2, 8, 0),
            "crawled_at": datetime(2026, 6, 6, 11, 5),
            "http_status": 403,
            "mime_type": "text/html",
        },
    )

    assert isinstance(source.metadata, UrlSourceMetadata)
    assert isinstance(source.error, SourceError)
    assert source.error.retryable is False
    assert source.error.failed_stage is ProcessingStage.downloading


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("source_id", ""),
        ("source_id", "   "),
        ("current_stage", None),
        ("created_at", None),
    ],
)
def test_source_detail_rejects_empty_or_null_required_fields(
    field_name: str,
    field_value: object,
) -> None:
    payload = {
        "source_id": "src_pdf_001",
        "source_type": "pdf",
        "status": "processing",
        "current_stage": "queued",
        "created_at": datetime(2026, 6, 6, 9, 30),
    }
    payload[field_name] = field_value

    with pytest.raises(ValidationError):
        SourceDetailResponse.model_validate(payload)


@pytest.mark.parametrize(
    "metadata",
    [
        {
            "metadata_type": "pdf",
            "original_filename": "",
        },
        {
            "metadata_type": "docx",
            "original_filename": "   ",
        },
        {
            "metadata_type": "url",
            "original_url": "",
            "domain": "example.com",
        },
        {
            "metadata_type": "url",
            "original_url": "https://example.com/article",
            "domain": "",
        },
    ],
)
def test_source_detail_rejects_empty_required_metadata_fields(
    metadata: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        SourceDetailResponse(
            source_id="src_001",
            source_type=SourceType.url,
            status=SourceStatus.processing,
            current_stage=ProcessingStage.queued,
            created_at=datetime(2026, 6, 6, 9, 30),
            metadata=metadata,
        )


@pytest.mark.parametrize(
    "payload",
    [
        {
            "error_code": "",
            "message": "The URL returned HTTP 403.",
            "failed_stage": "downloading",
        },
        {
            "error_code": "URL_HTTP_403",
            "message": "",
            "failed_stage": "downloading",
        },
        {
            "error_code": "URL_HTTP_403",
            "message": "The URL returned HTTP 403.",
            "failed_stage": None,
        },
    ],
)
def test_source_error_rejects_empty_or_null_required_fields(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        SourceError.model_validate(payload)


def test_source_detail_rejects_invalid_field_types() -> None:
    with pytest.raises(ValidationError):
        SourceDetailResponse(
            source_id="src_001",
            source_type="spreadsheet",
            status=SourceStatus.processing,
            current_stage=ProcessingStage.queued,
            created_at="not-a-datetime",
        )
