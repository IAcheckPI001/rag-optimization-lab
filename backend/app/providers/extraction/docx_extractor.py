from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError as MetadataPackageNotFoundError
from importlib.metadata import version
from io import BytesIO
import re
from zipfile import BadZipFile

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph
from lxml.etree import XMLSyntaxError
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


HEADING_STYLE_PATTERN = re.compile(r"^Heading ([1-9][0-9]*)$")
TABLE_SERIALIZATION_FORMAT = "tsv_escaped_v1"


@dataclass(frozen=True)
class _DocxBlock:
    block_type: str
    element: object
    block_index: int


class DocxExtractor:
    source_type = SourceType.docx
    extractor_name = "python-docx"

    def __init__(self, extractor_version: str | None = None) -> None:
        self.extractor_version = extractor_version or _get_python_docx_version()

    def extract(self, input_data: ExtractionInput) -> ExtractionResult:
        if input_data.source_type is not SourceType.docx:
            raise ExtractionSourceTypeMismatchError(
                "DocxExtractor requires source_type=docx.",
                details=_safe_input_details(input_data),
            )

        document = self._open_document(input_data)
        extracted_at = datetime.now(timezone.utc)

        units: list[RawDocumentUnit] = []
        warnings: list[ExtractionWarning] = []
        heading_state: dict[int, str] = {}

        paragraph_index = 0
        table_index = 0
        paragraph_count = 0
        heading_count = 0
        table_count = 0
        unsupported_item_count = 0
        skipped_items = 0
        total_body_items = 0

        for block in _iter_docx_body_blocks(document):
            total_body_items += 1

            if block.block_type == "paragraph":
                paragraph = block.element
                if not isinstance(paragraph, Paragraph):
                    raise ExtractionInvariantError("Invalid DOCX paragraph block.")

                current_paragraph_index = paragraph_index
                paragraph_index += 1
                paragraph_count += 1

                content = paragraph.text
                style_name = _paragraph_style_name(paragraph)
                heading_level = _heading_level(style_name)

                if not content.strip():
                    skipped_items += 1
                    continue

                block_type = "heading" if heading_level is not None else "paragraph"
                if heading_level is not None:
                    heading_state[heading_level] = content
                    heading_state = {
                        level: text
                        for level, text in heading_state.items()
                        if level <= heading_level
                    }
                    heading_count += 1

                heading_path = _heading_path(heading_state)
                metadata: dict[str, object] = {
                    "parser": self.extractor_name,
                    "parser_version": self.extractor_version,
                    "block_type": block_type,
                    "block_index": block.block_index,
                    "paragraph_index": current_paragraph_index,
                }
                if style_name:
                    metadata["style_name"] = style_name
                if heading_level is not None:
                    metadata["heading_level"] = heading_level

                units.append(
                    self._build_unit(
                        input_data=input_data,
                        unit_index=len(units),
                        content=content,
                        content_type=DocumentContentType.paragraph,
                        heading_path=heading_path,
                        extracted_at=extracted_at,
                        extra_metadata=metadata,
                    )
                )
                continue

            if block.block_type == "table":
                table = block.element
                if not isinstance(table, Table):
                    raise ExtractionInvariantError("Invalid DOCX table block.")

                current_table_index = table_index
                table_index += 1
                table_count += 1

                table_data = _serialize_table(table)
                if table_data.is_blank:
                    skipped_items += 1
                    continue

                metadata = {
                    "parser": self.extractor_name,
                    "parser_version": self.extractor_version,
                    "block_type": "table",
                    "block_index": block.block_index,
                    "table_index": current_table_index,
                    "row_count": table_data.row_count,
                    "column_count": table_data.column_count,
                    "row_column_counts": table_data.row_column_counts,
                    "serialization_format": TABLE_SERIALIZATION_FORMAT,
                }

                units.append(
                    self._build_unit(
                        input_data=input_data,
                        unit_index=len(units),
                        content=table_data.content,
                        content_type=DocumentContentType.table,
                        heading_path=_heading_path(heading_state),
                        extracted_at=extracted_at,
                        extra_metadata=metadata,
                    )
                )
                continue

            unsupported_item_count += 1
            skipped_items += 1
            warnings.append(
                ExtractionWarning(
                    warning_code="unsupported_docx_element",
                    message="Unsupported DOCX body element skipped.",
                    stage=ProcessingStage.extracting,
                    item_index=block.block_index,
                    extra_metadata={
                        "parser": self.extractor_name,
                        "parser_version": self.extractor_version,
                        "element_tag": block.block_type,
                    },
                )
            )

        if not units:
            raise ExtractionNoContentError(
                "DOCX content contains no extractable units.",
                details=_safe_input_details(input_data),
            )

        stats = ExtractionStats(
            total_units=len(units),
            skipped_items=skipped_items,
            warning_count=len(warnings),
            extra_metadata={
                "total_body_items": total_body_items,
                "paragraph_count": paragraph_count,
                "heading_count": heading_count,
                "table_count": table_count,
                "unsupported_item_count": unsupported_item_count,
            },
        )

        try:
            return ExtractionResult(
                source_id=input_data.source_id,
                document_id=input_data.document_id,
                source_type=SourceType.docx,
                extractor_name=self.extractor_name,
                extractor_version=self.extractor_version,
                units=units,
                warnings=warnings,
                stats=stats,
            )
        except ValidationError as exc:
            raise ExtractionInvariantError(
                "DOCX extractor produced an invalid ExtractionResult.",
                details={
                    "source_id": input_data.source_id,
                    "document_id": input_data.document_id,
                    "unit_count": len(units),
                    "warning_count": len(warnings),
                },
            ) from exc

    def _open_document(self, input_data: ExtractionInput):
        try:
            return Document(BytesIO(input_data.content_bytes))
        except (
            PackageNotFoundError,
            BadZipFile,
            KeyError,
            ValueError,
            XMLSyntaxError,
        ) as exc:
            raise ExtractionParsingError(
                "Unable to open DOCX content.",
                details=_safe_input_details(input_data),
            ) from exc

    def _build_unit(
        self,
        *,
        input_data: ExtractionInput,
        unit_index: int,
        content: str,
        content_type: DocumentContentType,
        heading_path: list[str],
        extracted_at: datetime,
        extra_metadata: dict[str, object],
    ) -> RawDocumentUnit:
        section = heading_path[-1] if heading_path else None
        return RawDocumentUnit(
            document_id=input_data.document_id,
            source_id=input_data.source_id,
            source_type=SourceType.docx,
            source_uri=input_data.source_uri,
            content=content,
            page_start=None,
            page_end=None,
            section=section,
            heading_path=list(heading_path),
            content_type=content_type,
            extra_metadata=extra_metadata,
            raw_unit_id=build_raw_unit_id(input_data.document_id, unit_index),
            unit_index=unit_index,
            extracted_at=extracted_at,
        )


@dataclass(frozen=True)
class _SerializedTable:
    content: str
    row_count: int
    column_count: int
    row_column_counts: list[int]
    is_blank: bool


def _get_python_docx_version() -> str:
    try:
        return version("python-docx")
    except MetadataPackageNotFoundError:
        return "unknown"


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


def _iter_docx_body_blocks(document) -> list[_DocxBlock]:
    blocks: list[_DocxBlock] = []
    block_index = 0
    body = document.element.body
    for child in body.iterchildren():
        if isinstance(child, CT_P):
            blocks.append(_DocxBlock("paragraph", Paragraph(child, document), block_index))
            block_index += 1
            continue
        if isinstance(child, CT_Tbl):
            blocks.append(_DocxBlock("table", Table(child, document), block_index))
            block_index += 1
            continue
        if child.tag.endswith("}sectPr"):
            continue

        blocks.append(_DocxBlock(child.tag, child, block_index))
        block_index += 1
    return blocks


def _paragraph_style_name(paragraph: Paragraph) -> str | None:
    style_name = getattr(getattr(paragraph, "style", None), "name", None)
    if isinstance(style_name, str) and style_name.strip():
        return style_name
    return None


def _heading_level(style_name: str | None) -> int | None:
    if not isinstance(style_name, str):
        return None
    match = HEADING_STYLE_PATTERN.match(style_name)
    if match is None:
        return None
    return int(match.group(1))


def _heading_path(heading_state: dict[int, str]) -> list[str]:
    return [heading_state[level] for level in sorted(heading_state)]


def _serialize_table(table: Table) -> _SerializedTable:
    rows: list[list[str]] = []
    raw_cell_texts: list[str] = []
    row_column_counts: list[int] = []

    for row in table.rows:
        cells = row.cells
        row_column_counts.append(len(cells))
        row_values: list[str] = []
        for cell in cells:
            cell_text = cell.text
            raw_cell_texts.append(cell_text)
            row_values.append(_escape_tsv_cell(cell_text))
        rows.append(row_values)

    is_blank = all(not cell_text.strip() for cell_text in raw_cell_texts)
    serialized_rows = ["\t".join(row) for row in rows]

    return _SerializedTable(
        content="\n".join(serialized_rows),
        row_count=len(rows),
        column_count=max(row_column_counts, default=0),
        row_column_counts=row_column_counts,
        is_blank=is_blank,
    )


def _escape_tsv_cell(cell_text: str) -> str:
    return (
        cell_text.replace("\\", "\\\\")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\t", "\\t")
        .replace("\n", "\\n")
    )
