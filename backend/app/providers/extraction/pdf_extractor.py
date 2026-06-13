from __future__ import annotations

from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError as MetadataPackageNotFoundError
from importlib.metadata import version
from math import isfinite
from numbers import Real

import pymupdf
from pydantic import ValidationError

from app.providers.extraction.errors import (
    ExtractionInvariantError,
    ExtractionNoContentError,
    ExtractionParsingError,
    ExtractionSourceTypeMismatchError,
)
from app.providers.extraction.ids import build_raw_unit_id
from app.schemas.document import DocumentContentType, RawDocumentUnit
from app.schemas.extraction import (
    ExtractionInput,
    ExtractionResult,
    ExtractionStats,
    ExtractionWarning,
)
from app.schemas.source import ProcessingStage, SourceType


_PYMUPDF_OPEN_ERRORS: tuple[type[BaseException], ...] = tuple(
    error_type
    for error_type in (
        getattr(pymupdf, "FileDataError", None),
        getattr(pymupdf, "EmptyFileError", None),
        RuntimeError,
        ValueError,
    )
    if isinstance(error_type, type) and issubclass(error_type, BaseException)
)


class PdfExtractor:
    source_type = SourceType.pdf
    extractor_name = "pymupdf"

    def __init__(self, extractor_version: str | None = None) -> None:
        self.extractor_version = extractor_version or _get_pymupdf_version()

    def extract(self, input_data: ExtractionInput) -> ExtractionResult:
        if input_data.source_type is not SourceType.pdf:
            raise ExtractionSourceTypeMismatchError(
                "PdfExtractor requires source_type=pdf.",
                details=_safe_input_details(input_data),
            )

        document = self._open_document(input_data)
        try:
            self._ensure_document_is_readable(document, input_data)
            return self._extract_open_document(document, input_data)
        finally:
            document.close()

    def _open_document(self, input_data: ExtractionInput):
        try:
            return pymupdf.open(stream=input_data.content_bytes, filetype="pdf")
        except _PYMUPDF_OPEN_ERRORS as exc:
            raise ExtractionParsingError(
                "Unable to open PDF content.",
                details=_safe_input_details(input_data),
            ) from exc

    def _ensure_document_is_readable(
        self, document, input_data: ExtractionInput
    ) -> None:
        if not bool(getattr(document, "needs_pass", False)):
            return

        authenticate = getattr(document, "authenticate", None)
        authenticated = authenticate("") if callable(authenticate) else 0
        if not authenticated:
            raise ExtractionParsingError(
                "PDF content requires a password.",
                details=_safe_input_details(input_data),
            )

    def _extract_open_document(
        self, document, input_data: ExtractionInput
    ) -> ExtractionResult:
        extracted_at = datetime.now(timezone.utc)

        units: list[RawDocumentUnit] = []
        warnings: list[ExtractionWarning] = []

        skipped_items = 0
        blank_page_count = 0
        pages_with_text_count = 0
        total_observed_blocks = 0
        text_block_count = 0
        blank_text_block_count = 0
        non_text_block_count = 0
        document_block_index = 0

        page_count = len(document)

        for page_index in range(page_count):
            page = document[page_index]
            page_number = page_index + 1
            emitted_on_page = 0

            try:
                blocks = page.get_text("blocks", sort=True)
            except _PYMUPDF_OPEN_ERRORS as exc:
                raise ExtractionParsingError(
                    "Unable to extract PDF page text.",
                    details={
                        **_safe_input_details(input_data),
                        "page_index": page_index,
                        "page_number": page_number,
                    },
                ) from exc

            for page_block_index, block in enumerate(blocks):
                total_observed_blocks += 1
                current_document_block_index = document_block_index
                document_block_index += 1

                block_type = _block_type(block)
                if block_type is not None and block_type != 0:
                    non_text_block_count += 1
                    skipped_items += 1
                    continue

                content = _block_text(block)
                if content is None:
                    skipped_items += 1
                    warnings.append(
                        _malformed_block_warning(
                            extractor_name=self.extractor_name,
                            extractor_version=self.extractor_version,
                            page_index=page_index,
                            page_number=page_number,
                            page_block_index=page_block_index,
                            document_block_index=current_document_block_index,
                            pymupdf_block_type=block_type,
                            message="PDF block text is missing or invalid.",
                        )
                    )
                    continue

                text_block_count += 1

                if not content.strip():
                    blank_text_block_count += 1
                    skipped_items += 1
                    continue

                bbox = _block_bbox(block)
                if bbox is None:
                    skipped_items += 1
                    warnings.append(
                        _malformed_block_warning(
                            extractor_name=self.extractor_name,
                            extractor_version=self.extractor_version,
                            page_index=page_index,
                            page_number=page_number,
                            page_block_index=page_block_index,
                            document_block_index=current_document_block_index,
                            pymupdf_block_type=block_type,
                            message="PDF block bounding box is missing or invalid.",
                        )
                    )
                    continue

                metadata: dict[str, object] = {
                    "parser": self.extractor_name,
                    "parser_version": self.extractor_version,
                    "block_type": "text",
                    "page_index": page_index,
                    "page_number": page_number,
                    "page_block_index": page_block_index,
                    "bbox": bbox,
                    "document_block_index": current_document_block_index,
                }

                block_number = _block_number(block)
                if block_number is not None:
                    metadata["pymupdf_block_number"] = block_number
                if block_type is not None:
                    metadata["pymupdf_block_type"] = block_type

                units.append(
                    RawDocumentUnit(
                        document_id=input_data.document_id,
                        source_id=input_data.source_id,
                        source_type=SourceType.pdf,
                        source_uri=input_data.source_uri,
                        content=content,
                        page_start=page_number,
                        page_end=page_number,
                        section=None,
                        heading_path=[],
                        content_type=DocumentContentType.paragraph,
                        extra_metadata=metadata,
                        raw_unit_id=build_raw_unit_id(
                            input_data.document_id, len(units)
                        ),
                        unit_index=len(units),
                        extracted_at=extracted_at,
                    )
                )
                emitted_on_page += 1

            if emitted_on_page:
                pages_with_text_count += 1
            else:
                blank_page_count += 1

        if not units:
            raise ExtractionNoContentError(
                "PDF content contains no extractable text units.",
                details={
                    **_safe_input_details(input_data),
                    "page_count": page_count,
                    "blank_page_count": blank_page_count,
                    "total_observed_blocks": total_observed_blocks,
                    "text_block_count": text_block_count,
                    "blank_text_block_count": blank_text_block_count,
                    "non_text_block_count": non_text_block_count,
                },
            )

        stats = ExtractionStats(
            total_units=len(units),
            skipped_items=skipped_items,
            warning_count=len(warnings),
            extra_metadata={
                "page_count": page_count,
                "blank_page_count": blank_page_count,
                "pages_with_text_count": pages_with_text_count,
                "total_observed_blocks": total_observed_blocks,
                "text_block_count": text_block_count,
                "blank_text_block_count": blank_text_block_count,
                "non_text_block_count": non_text_block_count,
            },
        )

        try:
            return ExtractionResult(
                source_id=input_data.source_id,
                document_id=input_data.document_id,
                source_type=SourceType.pdf,
                extractor_name=self.extractor_name,
                extractor_version=self.extractor_version,
                units=units,
                warnings=warnings,
                stats=stats,
            )
        except ValidationError as exc:
            raise ExtractionInvariantError(
                "PDF extractor produced an invalid ExtractionResult.",
                details={
                    "source_id": input_data.source_id,
                    "document_id": input_data.document_id,
                    "unit_count": len(units),
                    "warning_count": len(warnings),
                },
            ) from exc


def _get_pymupdf_version() -> str:
    try:
        return version("PyMuPDF")
    except MetadataPackageNotFoundError as exc:
        raise ExtractionInvariantError(
            "PyMuPDF package metadata is unavailable.",
            details={"package_name": "PyMuPDF"},
        ) from exc


def _safe_input_details(input_data: ExtractionInput) -> dict[str, object]:
    details: dict[str, object] = {
        "source_id": input_data.source_id,
        "document_id": input_data.document_id,
        "source_type": input_data.source_type.value,
    }
    if input_data.original_filename:
        details["original_filename"] = input_data.original_filename
    if input_data.media_type:
        details["media_type"] = input_data.media_type
    return details


def _block_bbox(block: object) -> list[float] | None:
    if not isinstance(block, (list, tuple)) or len(block) < 4:
        return None

    values = block[:4]
    if not all(isinstance(value, Real) and isfinite(value) for value in values):
        return None

    return [float(value) for value in values]


def _block_text(block: object) -> str | None:
    if not isinstance(block, (list, tuple)) or len(block) < 5:
        return None

    content = block[4]
    if not isinstance(content, str):
        return None
    return content


def _block_number(block: object) -> int | None:
    if not isinstance(block, (list, tuple)) or len(block) < 6:
        return None

    block_number = block[5]
    if isinstance(block_number, int):
        return block_number
    return None


def _block_type(block: object) -> int | None:
    if not isinstance(block, (list, tuple)) or len(block) < 7:
        return None

    block_type = block[6]
    if isinstance(block_type, int):
        return block_type
    return None


def _malformed_block_warning(
    *,
    extractor_name: str,
    extractor_version: str,
    page_index: int,
    page_number: int,
    page_block_index: int,
    document_block_index: int,
    pymupdf_block_type: int | None,
    message: str,
) -> ExtractionWarning:
    metadata: dict[str, object] = {
        "parser": extractor_name,
        "parser_version": extractor_version,
        "page_index": page_index,
        "page_number": page_number,
        "page_block_index": page_block_index,
    }
    if pymupdf_block_type is not None:
        metadata["pymupdf_block_type"] = pymupdf_block_type

    return ExtractionWarning(
        warning_code="malformed_pdf_block",
        message=message,
        stage=ProcessingStage.extracting,
        item_index=document_block_index,
        extra_metadata=metadata,
    )
