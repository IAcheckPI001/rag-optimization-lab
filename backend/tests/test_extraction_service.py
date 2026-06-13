from io import BytesIO
from datetime import datetime, timezone

import pytest

from docx import Document
import pymupdf

from app.providers.extraction.docx_extractor import DocxExtractor
from app.providers.extraction.errors import (
    ExtractionNoContentError,
    ExtractionParsingError,
)
from app.providers.extraction.html_extractor import HtmlExtractor
from app.providers.extraction.interface import ContentExtractor
from app.providers.extraction.pdf_extractor import PdfExtractor
from app.providers.fetching.errors import UrlNetworkError, UrlSecurityError
from app.schemas.document import DocumentContentType, RawDocumentUnit
from app.schemas.extraction import (
    ExtractionInput,
    ExtractionResult,
    ExtractionStats,
    FetchedContent,
)
from app.schemas.source import ProcessingStage, SourceType
from app.services.extraction import (
    ExtractionService,
    ExtractionServiceError,
    ExtractorNotRegisteredError,
    ExtractorRegistry,
    map_to_source_error,
)


def docx_bytes(text: str = "DOCX body") -> bytes:
    document = Document()
    document.add_paragraph(text)
    stream = BytesIO()
    document.save(stream)
    return stream.getvalue()


def pdf_bytes(text: str = "PDF body") -> bytes:
    document = pymupdf.open()
    try:
        page = document.new_page()
        page.insert_text((72, 72), text)
        return document.tobytes()
    finally:
        document.close()


def minimal_result(input_data: ExtractionInput, content: str = "Extracted"):
    unit = RawDocumentUnit(
        document_id=input_data.document_id,
        source_id=input_data.source_id,
        source_type=input_data.source_type,
        source_uri=input_data.source_uri,
        content=content,
        section=None,
        heading_path=[],
        content_type=DocumentContentType.paragraph,
        extra_metadata={"block_type": "fake"},
        raw_unit_id=f"raw:{input_data.document_id}:000000",
        unit_index=0,
        extracted_at=datetime.now(timezone.utc),
    )
    return ExtractionResult(
        source_id=input_data.source_id,
        document_id=input_data.document_id,
        source_type=input_data.source_type,
        extractor_name="fake",
        extractor_version="test",
        units=[unit],
        stats=ExtractionStats(total_units=1, warning_count=0),
    )


class CapturingExtractor:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.inputs: list[ExtractionInput] = []

    def extract(self, input_data: ExtractionInput) -> ExtractionResult:
        self.inputs.append(input_data)
        if self.error is not None:
            raise self.error
        return minimal_result(input_data)


class FakeUrlFetcher:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.urls: list[str] = []

    def fetch(self, url: str) -> FetchedContent:
        self.urls.append(url)
        if self.error is not None:
            raise self.error
        return FetchedContent(
            original_url=url,
            final_url="https://example.com/final",
            content_bytes=b"<html><body><main><p>Fetched body</p></main></body></html>",
            media_type="text/html",
            charset="utf-8",
            status_code=200,
            redirect_count=1,
            extra_metadata={"downloaded_bytes": 57},
        )


def service_with(
    extractors: dict[SourceType, object],
    *,
    fetcher: FakeUrlFetcher | None = None,
) -> ExtractionService:
    return ExtractionService(
        registry=ExtractorRegistry(extractors),
        url_fetcher=fetcher or FakeUrlFetcher(),
    )


def assert_core_result_contract(result: ExtractionResult) -> None:
    assert result.stats.total_units == len(result.units)
    assert result.stats.warning_count == len(result.warnings)
    assert [unit.unit_index for unit in result.units] == list(range(len(result.units)))
    assert len({unit.raw_unit_id for unit in result.units}) == len(result.units)
    assert all(unit.source_id == result.source_id for unit in result.units)
    assert all(unit.document_id == result.document_id for unit in result.units)
    assert all(unit.source_type is result.source_type for unit in result.units)
    assert all(unit.content.strip() for unit in result.units)
    assert len({unit.extracted_at for unit in result.units}) == 1
    assert all(unit.character_count == len(unit.content) for unit in result.units)
    assert all(unit.word_count >= 1 for unit in result.units)
    assert all(unit.content_hash for unit in result.units)


def test_content_extractor_protocol_is_runtime_checkable_for_diagnostics() -> None:
    assert isinstance(CapturingExtractor(), ContentExtractor)


def test_registry_returns_registered_extractors_by_source_type() -> None:
    docx = CapturingExtractor()
    pdf = CapturingExtractor()
    html = CapturingExtractor()
    registry = ExtractorRegistry(
        {
            SourceType.docx: docx,
            SourceType.pdf: pdf,
            SourceType.url: html,
        }
    )

    assert registry.get(SourceType.docx) is docx
    assert registry.get(SourceType.pdf) is pdf
    assert registry.get(SourceType.url) is html


def test_registry_fails_for_unregistered_source_type() -> None:
    with pytest.raises(ExtractorNotRegisteredError) as exc_info:
        ExtractorRegistry({}).get(SourceType.pdf)

    assert exc_info.value.error_code == "extractor_not_registered"


def test_extract_bytes_builds_input_and_calls_registered_extractor() -> None:
    extractor = CapturingExtractor()
    service = service_with({SourceType.pdf: extractor})

    result = service.extract_bytes(
        source_id="src_001",
        document_id="doc_001",
        source_type=SourceType.pdf,
        source_uri="storage://source.pdf",
        original_filename="source.pdf",
        media_type="application/pdf",
        charset=None,
        content_bytes=b"%PDF fake",
        extractor_config={"mode": "test"},
        extra_metadata={"caller": {"batch": "one"}},
    )

    input_data = extractor.inputs[0]
    assert result.source_type is SourceType.pdf
    assert input_data.source_id == "src_001"
    assert input_data.document_id == "doc_001"
    assert input_data.source_type is SourceType.pdf
    assert input_data.source_uri == "storage://source.pdf"
    assert input_data.original_filename == "source.pdf"
    assert input_data.media_type == "application/pdf"
    assert input_data.extractor_config == {"mode": "test"}
    assert input_data.extra_metadata == {"caller": {"batch": "one"}}


def test_extract_bytes_rejects_url_source_type() -> None:
    service = service_with({SourceType.url: CapturingExtractor()})

    with pytest.raises(ExtractionServiceError) as exc_info:
        service.extract_bytes(
            source_id="src_001",
            document_id="doc_001",
            source_type=SourceType.url,
            content_bytes=b"<html/>",
        )

    source_error = exc_info.value.source_error
    assert source_error.error_code == "extraction_service_input_error"
    assert source_error.failed_stage is ProcessingStage.extracting
    assert source_error.retryable is False


def test_extract_url_fetches_before_html_extraction_and_uses_final_url() -> None:
    extractor = CapturingExtractor()
    fetcher = FakeUrlFetcher()
    service = service_with({SourceType.url: extractor}, fetcher=fetcher)

    result = service.extract_url(
        source_id="src_url",
        document_id="doc_url",
        url="https://example.com/original",
        extractor_config={"html": True},
        extra_metadata={"caller": "value"},
    )

    assert fetcher.urls == ["https://example.com/original"]
    input_data = extractor.inputs[0]
    assert result.source_type is SourceType.url
    assert input_data.source_type is SourceType.url
    assert input_data.source_uri == "https://example.com/final"
    assert input_data.media_type == "text/html"
    assert input_data.charset == "utf-8"
    assert input_data.content_bytes.startswith(b"<html>")
    assert input_data.extractor_config == {"html": True}
    assert input_data.extra_metadata["caller"] == "value"
    assert input_data.extra_metadata["fetch"]["status_code"] == 200
    assert input_data.extra_metadata["fetch"]["redirect_count"] == 1
    assert "content_bytes" not in input_data.extra_metadata["fetch"]


@pytest.mark.parametrize("reserved_key", ["fetch", "service"])
def test_service_rejects_reserved_metadata_keys(reserved_key: str) -> None:
    service = service_with({SourceType.url: CapturingExtractor()})

    with pytest.raises(ExtractionServiceError) as exc_info:
        service.extract_url(
            source_id="src_001",
            document_id="doc_001",
            url="https://example.com",
            extra_metadata={reserved_key: {"status_code": 999}},
        )

    source_error = exc_info.value.source_error
    assert source_error.error_code == "extraction_service_input_error"
    assert source_error.failed_stage is ProcessingStage.extracting


def test_fetching_provider_error_maps_to_source_error_with_cause() -> None:
    provider_error = UrlNetworkError(
        "DNS failed.",
        error_code="dns_resolution_failed",
        retryable=True,
    )
    service = service_with(
        {SourceType.url: CapturingExtractor()},
        fetcher=FakeUrlFetcher(error=provider_error),
    )

    with pytest.raises(ExtractionServiceError) as exc_info:
        service.extract_url(
            source_id="src_001",
            document_id="doc_001",
            url="https://example.com",
        )

    assert exc_info.value.__cause__ is provider_error
    source_error = exc_info.value.source_error
    assert source_error.error_code == "dns_resolution_failed"
    assert source_error.message == "DNS failed."
    assert source_error.retryable is True
    assert source_error.failed_stage is ProcessingStage.downloading


def test_fetching_security_error_maps_to_downloading_stage() -> None:
    source_error = map_to_source_error(
        UrlSecurityError("Blocked.", error_code="blocked_destination")
    )

    assert source_error.error_code == "blocked_destination"
    assert source_error.failed_stage is ProcessingStage.downloading
    assert source_error.retryable is False


@pytest.mark.parametrize(
    "provider_error, expected_stage",
    [
        (
            ExtractionParsingError("Cannot parse."),
            ProcessingStage.parsing,
        ),
        (
            ExtractionNoContentError("No content."),
            ProcessingStage.extracting,
        ),
    ],
)
def test_extraction_provider_errors_map_to_source_error_with_cause(
    provider_error: Exception,
    expected_stage: ProcessingStage,
) -> None:
    service = service_with(
        {SourceType.pdf: CapturingExtractor(error=provider_error)}
    )

    with pytest.raises(ExtractionServiceError) as exc_info:
        service.extract_bytes(
            source_id="src_001",
            document_id="doc_001",
            source_type=SourceType.pdf,
            content_bytes=b"%PDF fake",
        )

    assert exc_info.value.__cause__ is provider_error
    source_error = exc_info.value.source_error
    assert source_error.error_code == provider_error.error_code
    assert source_error.retryable is False
    assert source_error.failed_stage is expected_stage


def test_real_docx_pdf_and_url_html_service_paths_return_valid_results() -> None:
    service = service_with(
        {
            SourceType.docx: DocxExtractor(extractor_version="test-docx"),
            SourceType.pdf: PdfExtractor(extractor_version="test-pdf"),
            SourceType.url: HtmlExtractor(extractor_version="test-html"),
        }
    )

    docx_result = service.extract_bytes(
        source_id="src_docx",
        document_id="doc_docx",
        source_type=SourceType.docx,
        source_uri="storage://docx",
        original_filename="source.docx",
        media_type=(
            "application/vnd.openxmlformats-officedocument"
            ".wordprocessingml.document"
        ),
        content_bytes=docx_bytes("DOCX body"),
    )
    pdf_result = service.extract_bytes(
        source_id="src_pdf",
        document_id="doc_pdf",
        source_type=SourceType.pdf,
        source_uri="storage://pdf",
        original_filename="source.pdf",
        media_type="application/pdf",
        content_bytes=pdf_bytes("PDF body"),
    )
    html_result = service.extract_url(
        source_id="src_url",
        document_id="doc_url",
        url="https://example.com/article",
    )

    assert_core_result_contract(docx_result)
    assert_core_result_contract(pdf_result)
    assert_core_result_contract(html_result)
    assert {unit.page_start for unit in docx_result.units} == {None}
    assert {unit.page_start for unit in html_result.units} == {None}
    assert all(unit.page_start == unit.page_end for unit in pdf_result.units)
    assert all(unit.page_start is not None for unit in pdf_result.units)
    assert {unit.source_uri for unit in html_result.units} == {
        "https://example.com/final"
    }
