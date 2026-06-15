from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
import re
import unicodedata

from app.rag.cleaning.table_text import TSV_ESCAPED_V1, parse_tsv_escaped_v1, serialize_tsv_escaped_v1
from app.schemas.document import DocumentContentType


UNICODE_NFC = "unicode_nfc"
LINE_ENDINGS_NORMALIZED = "line_endings_normalized"
CONTROL_CHARACTERS_REMOVED = "control_characters_removed"
NBSP_NORMALIZED = "nbsp_normalized"
PROSE_WHITESPACE_NORMALIZED = "prose_whitespace_normalized"
LIST_WHITESPACE_NORMALIZED = "list_whitespace_normalized"
TABLE_CELLS_NORMALIZED = "table_cells_normalized"

REPLACEMENT_CHARACTER_DETECTED = "replacement_character_detected"
SUSPICIOUS_CONTROL_CHARACTERS_REMOVED = "suspicious_control_characters_removed"

HORIZONTAL_WHITESPACE_PATTERN = re.compile(r"[^\S\n]+")


@dataclass(frozen=True)
class NormalizationWarning:
    warning_code: str
    message: str
    extra_metadata: Mapping[str, object] | None = None


@dataclass(frozen=True)
class NormalizedContent:
    content: str
    transformations: tuple[str, ...]
    warnings: tuple[NormalizationWarning, ...] = ()


def normalize_content(
    content: str,
    *,
    content_type: DocumentContentType,
    extra_metadata: Mapping[str, object] | None = None,
) -> NormalizedContent:
    metadata = extra_metadata or {}

    if content_type is DocumentContentType.paragraph:
        return normalize_prose_content(content)

    if content_type is DocumentContentType.list:
        return normalize_list_content(content)

    if content_type is DocumentContentType.table:
        return normalize_table_content(content, extra_metadata=metadata)

    if content_type is DocumentContentType.code:
        return normalize_code_content(content)

    return normalize_unknown_content(content)


def normalize_prose_content(content: str) -> NormalizedContent:
    context = _NormalizationContext(content)
    context.detect_replacement_character()
    context.apply_unicode_nfc()
    context.apply_line_endings()
    context.apply_nbsp_normalization()
    context.apply_linewise_whitespace(PROSE_WHITESPACE_NORMALIZED)
    context.remove_unsafe_controls(preserve_tab=False)
    return context.to_result()


def normalize_list_content(content: str) -> NormalizedContent:
    context = _NormalizationContext(content)
    context.detect_replacement_character()
    context.apply_unicode_nfc()
    context.apply_line_endings()
    context.apply_nbsp_normalization()
    context.apply_linewise_whitespace(LIST_WHITESPACE_NORMALIZED)
    context.remove_unsafe_controls(preserve_tab=False)
    return context.to_result()


def normalize_table_content(
    content: str,
    *,
    extra_metadata: Mapping[str, object] | None = None,
) -> NormalizedContent:
    metadata = extra_metadata or {}
    if metadata.get("serialization_format") != TSV_ESCAPED_V1:
        return _preserve_unknown_table_content(content)

    context = _NormalizationContext(content)
    context.detect_replacement_character()
    context.apply_line_endings()

    rows = parse_tsv_escaped_v1(context.content)
    normalized_rows: list[list[str]] = []
    cell_transformations: list[str] = []
    cell_warnings: list[NormalizationWarning] = []
    cells_changed = False

    for row in rows:
        normalized_row: list[str] = []
        for cell in row:
            cell_result = _normalize_table_cell(cell)
            normalized_row.append(cell_result.content)
            cell_transformations.extend(cell_result.transformations)
            cell_warnings.extend(cell_result.warnings)
            cells_changed = cells_changed or cell_result.content != cell
        normalized_rows.append(normalized_row)

    serialized = serialize_tsv_escaped_v1(normalized_rows)
    if serialized != context.content:
        context.content = serialized

    for transformation in cell_transformations:
        context.add_transformation(transformation)

    if cells_changed:
        context.add_transformation(TABLE_CELLS_NORMALIZED)

    context.warnings.extend(cell_warnings)
    context.remove_unsafe_controls(preserve_tab=True)
    return context.to_result()


def normalize_code_content(content: str) -> NormalizedContent:
    context = _NormalizationContext(content)
    context.detect_replacement_character()
    context.apply_unicode_nfc()
    context.apply_line_endings()
    context.remove_unsafe_controls(preserve_tab=True)
    return context.to_result()


def normalize_unknown_content(content: str) -> NormalizedContent:
    context = _NormalizationContext(content)
    context.detect_replacement_character()
    context.apply_unicode_nfc()
    context.apply_line_endings()
    context.remove_unsafe_controls(preserve_tab=True)
    return context.to_result()


def _normalize_table_cell(cell: str) -> NormalizedContent:
    context = _NormalizationContext(cell)
    context.detect_replacement_character()
    context.apply_unicode_nfc()
    context.apply_line_endings()
    context.apply_nbsp_normalization()
    context.remove_unsafe_controls(preserve_tab=True)
    return context.to_result()


def _preserve_unknown_table_content(content: str) -> NormalizedContent:
    warnings = _replacement_character_warnings(content)
    return NormalizedContent(content=content, transformations=(), warnings=warnings)


class _NormalizationContext:
    def __init__(self, content: str) -> None:
        self.content = content
        self.transformations: list[str] = []
        self.warnings: list[NormalizationWarning] = []

    def detect_replacement_character(self) -> None:
        self.warnings.extend(_replacement_character_warnings(self.content))

    def apply_unicode_nfc(self) -> None:
        normalized = unicodedata.normalize("NFC", self.content)
        if normalized != self.content:
            self.content = normalized
            self.add_transformation(UNICODE_NFC)

    def apply_line_endings(self) -> None:
        normalized = self.content.replace("\r\n", "\n").replace("\r", "\n")
        if normalized != self.content:
            self.content = normalized
            self.add_transformation(LINE_ENDINGS_NORMALIZED)

    def apply_nbsp_normalization(self) -> None:
        normalized = self.content.replace("\xa0", " ")
        if normalized != self.content:
            self.content = normalized
            self.add_transformation(NBSP_NORMALIZED)

    def apply_linewise_whitespace(self, transformation_code: str) -> None:
        normalized_lines = [
            HORIZONTAL_WHITESPACE_PATTERN.sub(" ", line).strip()
            for line in self.content.split("\n")
        ]
        collapsed_lines = _collapse_repeated_blank_lines(normalized_lines)
        normalized = "\n".join(collapsed_lines).strip()
        if normalized != self.content:
            self.content = normalized
            self.add_transformation(transformation_code)

    def remove_unsafe_controls(self, *, preserve_tab: bool) -> None:
        normalized, removed_count = _remove_unsafe_controls(
            self.content,
            preserve_tab=preserve_tab,
        )
        if removed_count == 0:
            return

        self.content = normalized
        self.add_transformation(CONTROL_CHARACTERS_REMOVED)
        self.warnings.append(
            NormalizationWarning(
                warning_code=SUSPICIOUS_CONTROL_CHARACTERS_REMOVED,
                message="Unsafe control characters were removed.",
                extra_metadata={"removed_count": removed_count},
            )
        )

    def add_transformation(self, transformation: str) -> None:
        if transformation not in self.transformations:
            self.transformations.append(transformation)

    def to_result(self) -> NormalizedContent:
        return NormalizedContent(
            content=self.content,
            transformations=tuple(self.transformations),
            warnings=tuple(self.warnings),
        )


def _collapse_repeated_blank_lines(lines: list[str]) -> list[str]:
    collapsed: list[str] = []
    previous_was_blank = False

    for line in lines:
        is_blank = line == ""
        if is_blank and previous_was_blank:
            continue
        collapsed.append(line)
        previous_was_blank = is_blank

    return collapsed


def _remove_unsafe_controls(content: str, *, preserve_tab: bool) -> tuple[str, int]:
    pieces: list[str] = []
    removed_count = 0

    for character in content:
        codepoint = ord(character)
        if character == "\n":
            pieces.append(character)
            continue

        if preserve_tab and character == "\t":
            pieces.append(character)
            continue

        if codepoint < 32 or codepoint == 127:
            removed_count += 1
            continue

        pieces.append(character)

    return "".join(pieces), removed_count


def _replacement_character_warnings(
    content: str,
) -> tuple[NormalizationWarning, ...]:
    if "\ufffd" not in content:
        return ()

    return (
        NormalizationWarning(
            warning_code=REPLACEMENT_CHARACTER_DETECTED,
            message="Unicode replacement character was detected.",
            extra_metadata=None,
        ),
    )
