from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
from numbers import Real
import re

from app.schemas.document import RawDocumentUnit
from app.schemas.source import SourceType


HTML_READING_TIME = "html_reading_time"
HTML_UI_NOISE = "html_ui_noise"
PDF_PAGE_NUMBER = "pdf_page_number"
POSSIBLE_PAGE_NUMBER = "possible_page_number"

PDF_HEADER_BAND_RATIO = 0.10
PDF_FOOTER_BAND_RATIO = 0.10

HTML_UI_NOISE_TEXTS = frozenset(
    {
        "Link Copied!",
        "Copy Link",
        "Share",
        "Share this article",
    }
)
READING_TIME_PATTERN = re.compile(r"^\d+\s+(?:min|minute|minutes)\s+read$", re.IGNORECASE)


@dataclass(frozen=True)
class SourceFilterWarning:
    warning_code: str
    message: str
    extra_metadata: Mapping[str, object]


@dataclass(frozen=True)
class SourceFilterDecision:
    drop_reason_code: str | None = None
    drop_message: str | None = None
    warnings: tuple[SourceFilterWarning, ...] = ()


def apply_source_filters(
    raw_unit: RawDocumentUnit,
    normalized_content: str,
) -> SourceFilterDecision:
    if raw_unit.source_type is SourceType.url:
        return _filter_html(raw_unit, normalized_content)

    if raw_unit.source_type is SourceType.pdf:
        return _filter_pdf(raw_unit, normalized_content)

    return SourceFilterDecision()


def _filter_html(
    raw_unit: RawDocumentUnit,
    normalized_content: str,
) -> SourceFilterDecision:
    block_type = raw_unit.extra_metadata.get("block_type")
    if block_type != "container_text":
        return SourceFilterDecision()

    if READING_TIME_PATTERN.fullmatch(normalized_content):
        return SourceFilterDecision(
            drop_reason_code=HTML_READING_TIME,
            drop_message="HTML reading-time label was removed.",
        )

    if normalized_content in HTML_UI_NOISE_TEXTS:
        return SourceFilterDecision(
            drop_reason_code=HTML_UI_NOISE,
            drop_message="HTML UI noise was removed.",
        )

    return SourceFilterDecision()


def _filter_pdf(
    raw_unit: RawDocumentUnit,
    normalized_content: str,
) -> SourceFilterDecision:
    page_number = _consistent_page_number(raw_unit, normalized_content)
    if page_number is None:
        return SourceFilterDecision()

    metadata = raw_unit.extra_metadata
    bbox_value = metadata.get("bbox")
    has_bbox = bbox_value is not None
    has_page_dimensions = (
        metadata.get("page_width") is not None
        and metadata.get("page_height") is not None
    )

    page_width = _finite_positive_number(metadata.get("page_width"))
    page_height = _finite_positive_number(metadata.get("page_height"))
    bbox = _valid_bbox(bbox_value, page_width=page_width, page_height=page_height)

    if bbox is not None and page_width is not None and page_height is not None:
        edge_band = _edge_band(bbox, page_height)
        if edge_band == "footer":
            return SourceFilterDecision(
                drop_reason_code=PDF_PAGE_NUMBER,
                drop_message="PDF footer page number was removed.",
            )

        if edge_band == "header":
            return SourceFilterDecision(
                warnings=(
                    _possible_page_number_warning(
                        raw_unit,
                        page_number=page_number,
                        has_bbox=has_bbox,
                        has_page_dimensions=has_page_dimensions,
                        geometry_status="valid_header_band",
                        edge_band="header",
                    ),
                )
            )

        return SourceFilterDecision()

    if has_bbox and not has_page_dimensions:
        return SourceFilterDecision(
            warnings=(
                _possible_page_number_warning(
                    raw_unit,
                    page_number=page_number,
                    has_bbox=has_bbox,
                    has_page_dimensions=False,
                    geometry_status="missing_page_dimensions",
                    edge_band="unknown",
                ),
            )
        )

    if has_bbox and has_page_dimensions and (page_width is None or page_height is None):
        return SourceFilterDecision(
            warnings=(
                _possible_page_number_warning(
                    raw_unit,
                    page_number=page_number,
                    has_bbox=has_bbox,
                    has_page_dimensions=True,
                    geometry_status="invalid_page_dimensions",
                    edge_band="unknown",
                ),
            )
        )

    return SourceFilterDecision()


def _consistent_page_number(
    raw_unit: RawDocumentUnit,
    normalized_content: str,
) -> int | None:
    if raw_unit.page_start is None or raw_unit.page_end is None:
        return None

    if raw_unit.page_start != raw_unit.page_end:
        return None

    page_number = raw_unit.extra_metadata.get("page_number")
    if isinstance(page_number, bool) or not isinstance(page_number, int):
        return None

    if page_number != raw_unit.page_start:
        return None

    if normalized_content != str(page_number):
        return None

    return page_number


def _valid_bbox(
    value: object,
    *,
    page_width: float | None,
    page_height: float | None,
) -> tuple[float, float, float, float] | None:
    if page_width is None or page_height is None:
        return None

    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None

    numbers = tuple(_finite_real_number(item) for item in value)
    if any(item is None for item in numbers):
        return None

    x0, y0, x1, y1 = numbers
    if x0 is None or y0 is None or x1 is None or y1 is None:
        return None

    if x0 >= x1 or y0 >= y1:
        return None

    if not (0 <= x0 <= page_width and 0 <= x1 <= page_width):
        return None

    if not (0 <= y0 <= page_height and 0 <= y1 <= page_height):
        return None

    return (x0, y0, x1, y1)


def _finite_positive_number(value: object) -> float | None:
    number = _finite_real_number(value)
    if number is None or number <= 0:
        return None
    return number


def _finite_real_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None

    number = float(value)
    if not math.isfinite(number):
        return None

    return number


def _edge_band(
    bbox: tuple[float, float, float, float],
    page_height: float,
) -> str:
    _, y0, _, y1 = bbox
    if y1 <= page_height * PDF_HEADER_BAND_RATIO:
        return "header"

    if y0 >= page_height * (1 - PDF_FOOTER_BAND_RATIO):
        return "footer"

    return "middle"


def _possible_page_number_warning(
    raw_unit: RawDocumentUnit,
    *,
    page_number: int,
    has_bbox: bool,
    has_page_dimensions: bool,
    geometry_status: str,
    edge_band: str,
) -> SourceFilterWarning:
    return SourceFilterWarning(
        warning_code=POSSIBLE_PAGE_NUMBER,
        message="Possible PDF page number was preserved.",
        extra_metadata={
            "page_number": page_number,
            "page_start": raw_unit.page_start,
            "page_end": raw_unit.page_end,
            "has_bbox": has_bbox,
            "has_page_dimensions": has_page_dimensions,
            "geometry_status": geometry_status,
            "edge_band": edge_band,
        },
    )
