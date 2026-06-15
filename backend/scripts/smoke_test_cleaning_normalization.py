

from __future__ import annotations

import copy
import json
import sys
import unicodedata
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

# Cho phép chạy trực tiếp từ backend/scripts.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.rag.cleaning.normalization import (  # noqa: E402
    NormalizedContent,
    normalize_content,
)
from app.schemas.document import DocumentContentType  # noqa: E402


class SmokeCheckError(AssertionError):
    """Raised when a Phase 3.2 smoke-check invariant fails."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeCheckError(message)


def visible_text(value: str) -> str:
    """
    Return a readable representation that exposes tabs, newlines,
    carriage returns, control characters, and NBSP.
    """
    return value.encode("unicode_escape").decode("ascii")


def warning_to_dict(warning: object) -> dict[str, Any]:
    if is_dataclass(warning):
        return asdict(warning)

    code = getattr(warning, "code", None)
    message = getattr(warning, "message", None)
    extra_metadata = getattr(warning, "extra_metadata", None)

    result: dict[str, Any] = {
        "code": code,
        "message": message,
    }

    if extra_metadata is not None:
        result["extra_metadata"] = dict(extra_metadata)

    return result


def result_to_dict(result: NormalizedContent) -> dict[str, Any]:
    return {
        "content": result.content,
        "content_visible": visible_text(result.content),
        "transformations": list(result.transformations),
        "warnings": [
            warning_to_dict(warning)
            for warning in result.warnings
        ],
    }


def validate_output_contract(result: NormalizedContent) -> None:
    require(
        isinstance(result, NormalizedContent),
        f"Expected NormalizedContent, got {type(result).__name__}.",
    )
    require(
        isinstance(result.content, str),
        "NormalizedContent.content must be str.",
    )
    require(
        isinstance(result.transformations, tuple),
        "NormalizedContent.transformations must be tuple.",
    )
    require(
        isinstance(result.warnings, tuple),
        "NormalizedContent.warnings must be tuple.",
    )
    require(
        all(
            isinstance(code, str) and code.strip()
            for code in result.transformations
        ),
        "Every transformation code must be a non-empty string.",
    )
    require(
        len(result.transformations) == len(set(result.transformations)),
        "Transformation codes must not contain duplicates.",
    )


def normalize_case(
    *,
    name: str,
    content: str,
    content_type: DocumentContentType,
    extra_metadata: dict[str, object] | None = None,
) -> tuple[NormalizedContent, dict[str, Any]]:
    metadata = extra_metadata or {}
    original_metadata = copy.deepcopy(metadata)

    result = normalize_content(
        content,
        content_type=content_type,
        extra_metadata=metadata,
    )
    print(result.warnings)
    print(repr(result.warnings))

    validate_output_contract(result)

    require(
        metadata == original_metadata,
        f"{name}: normalize_content mutated input metadata.",
    )

    changed = result.content != content

    require(
        bool(result.transformations) == changed,
        (
            f"{name}: transformations must exist exactly when output content "
            "differs from input content."
        ),
    )

    second_result = normalize_content(
        result.content,
        content_type=content_type,
        extra_metadata=metadata,
    )

    validate_output_contract(second_result)

    require(
        second_result.content == result.content,
        f"{name}: content normalization is not idempotent.",
    )
    require(
        second_result.transformations == (),
        (
            f"{name}: second normalization pass produced content-changing "
            f"transformations: {second_result.transformations!r}."
        ),
    )

    report = {
        "name": name,
        "content_type": str(content_type.value),
        "metadata": metadata,
        "input": {
            "content": content,
            "content_visible": visible_text(content),
            "character_count": len(content),
        },
        "output": {
            **result_to_dict(result),
            "character_count": len(result.content),
            "changed": changed,
        },
        "idempotency": {
            "content_stable": second_result.content == result.content,
            "second_pass_transformations": list(
                second_result.transformations
            ),
            "second_pass_warnings": [
                warning_to_dict(warning)
                for warning in second_result.warnings
            ],
        },
    }

    return result, report


def run_prose_case() -> dict[str, Any]:
    decomposed_vietnamese = unicodedata.normalize(
        "NFD",
        "Thủ tục đăng ký",
    )

    content = (
        f"  {decomposed_vietnamese}\t\ttrực tuyến\u00a0 \r\n"
        "\r\n"
        "\r\n"
        "  Tại cơ quan\x00  "
    )

    result, report = normalize_case(
        name="prose_normalization",
        content=content,
        content_type=DocumentContentType.paragraph,
        extra_metadata={"block_type": "paragraph"},
    )

    require(
        result.content == "Thủ tục đăng ký trực tuyến\n\nTại cơ quan",
        "Prose output does not match the expected normalized content.",
    )
    require(
        "unicode_nfc" in result.transformations,
        "Prose case should include unicode_nfc.",
    )
    require(
        "line_endings_normalized" in result.transformations,
        "Prose case should include line_endings_normalized.",
    )
    require(
        "control_characters_removed" in result.transformations,
        "Prose case should include control_characters_removed.",
    )
    require(
        "nbsp_normalized" in result.transformations,
        "Prose case should include nbsp_normalized.",
    )
    require(
        "prose_whitespace_normalized" in result.transformations,
        "Prose case should include prose_whitespace_normalized.",
    )

    return report


def run_list_case() -> dict[str, Any]:
    content = "\tNộp\t\thồ sơ\u00a0 trực tuyến  "

    result, report = normalize_case(
        name="list_normalization",
        content=content,
        content_type=DocumentContentType.list,
        extra_metadata={
            "block_type": "list_item",
            "list_depth": 1,
        },
    )

    require(
        result.content == "Nộp hồ sơ trực tuyến",
        "List output does not match expected content.",
    )
    require(
        "\t" not in result.content,
        "List output must collapse tabs into spaces.",
    )
    require(
        "list_whitespace_normalized" in result.transformations,
        "List case should include list_whitespace_normalized.",
    )

    return report


def run_table_case() -> dict[str, Any]:
    # Real TAB separates columns.
    # Real LF separates rows.
    # Escaped \\t, \\n and \\\\ belong to cell content.
    content = (
        "Tên\tGhi chú\n"
        "A\u00a0B\tDòng 1\\nDòng 2\n"
        "Đường dẫn\tC:\\\\temp\\tdata\n"
        "\tÔ cuối"
    )

    result, report = normalize_case(
        name="table_tsv_escaped_v1",
        content=content,
        content_type=DocumentContentType.table,
        extra_metadata={
            "block_type": "table",
            "serialization_format": "tsv_escaped_v1",
        },
    )

    require(
        result.content.count("\t") == content.count("\t"),
        "Table real column delimiters were not preserved.",
    )
    require(
        result.content.count("\n") == content.count("\n"),
        "Table real row delimiters were not preserved.",
    )
    require(
        "\\n" in result.content,
        "Escaped newline semantics inside table cells were not preserved.",
    )
    require(
        "\\t" in result.content,
        "Escaped tab semantics inside table cells were not preserved.",
    )
    require(
        "\\\\" in result.content,
        "Escaped backslash semantics were not preserved.",
    )
    require(
        result.content.startswith("Tên\tGhi chú"),
        "Table structure or first row changed unexpectedly.",
    )
    require(
        result.content.endswith("\tÔ cuối"),
        "Leading empty table cell was not preserved.",
    )
    require(
        "table_cells_normalized" in result.transformations,
        "Table case should include table_cells_normalized.",
    )

    return report


def run_code_case() -> dict[str, Any]:
    content = (
        "\n"
        "\tdef run():\r\n"
        "\t\tvalue  =  1\u00a0\r\n"
        "\t\treturn value\n"
        "\n"
    )

    result, report = normalize_case(
        name="code_preservation",
        content=content,
        content_type=DocumentContentType.code,
        extra_metadata={"block_type": "code"},
    )

    require(
        result.content.startswith("\n\tdef run():\n"),
        "Code outer blank line, tab, or line ending was not preserved correctly.",
    )
    require(
        "\t\tvalue  =  1\u00a0\n" in result.content,
        "Code indentation, repeated spaces, or NBSP was changed.",
    )
    require(
        result.content.endswith("\n\n"),
        "Code outer blank lines should remain unchanged by default.",
    )
    require(
        "line_endings_normalized" in result.transformations,
        "Code case should include line_endings_normalized.",
    )
    require(
        "code_outer_blank_lines_trimmed" not in result.transformations,
        "Code outer blank lines must not be trimmed by default.",
    )

    return report


def run_unknown_case() -> dict[str, Any]:
    content = "A\tB\u00a0C\r\nD\x00"

    result, report = normalize_case(
        name="unknown_conservative_fallback",
        content=content,
        content_type=DocumentContentType.unknown,
        extra_metadata={"block_type": "unknown"},
    )

    require(
        "\t" in result.content,
        "Unknown content must preserve tabs.",
    )
    require(
        "\u00a0" in result.content,
        "Unknown content must preserve NBSP.",
    )
    require(
        "\x00" not in result.content,
        "Unknown content must remove unsafe control characters.",
    )
    require(
        "\r" not in result.content,
        "Unknown content must normalize CRLF/CR.",
    )

    return report

def get_warning_code(warning: object) -> str | None:
    return getattr(
        warning,
        "warning_code",
        getattr(warning, "code", None),
    )

def run_warning_case() -> dict[str, Any]:
    content = "Dữ liệu có ký tự thay thế \ufffd"

    result, report = normalize_case(
        name="replacement_character_warning",
        content=content,
        content_type=DocumentContentType.paragraph,
        extra_metadata={"block_type": "paragraph"},
    )

    warning_codes = {
        get_warning_code(warning)
        for warning in result.warnings
    }

    require(
        "replacement_character_detected" in warning_codes,
        "Expected replacement_character_detected warning.",
    )
    require(
        result.content == content,
        "Replacement-character detection must not rewrite content.",
    )
    require(
        result.transformations == (),
        "Warning-only case must not contain transformations.",
    )

    return report


def run_unchanged_case() -> dict[str, Any]:
    content = "Nội dung đã chuẩn hóa."

    result, report = normalize_case(
        name="already_normalized",
        content=content,
        content_type=DocumentContentType.paragraph,
        extra_metadata={"block_type": "paragraph"},
    )

    require(
        result.content == content,
        "Already-normalized content must remain unchanged.",
    )
    require(
        result.transformations == (),
        "Already-normalized content must not report transformations.",
    )
    require(
        result.warnings == (),
        "Already-normalized content should not report warnings.",
    )

    return report


def main() -> int:
    cases = [
        run_prose_case,
        run_list_case,
        run_table_case,
        run_code_case,
        run_unknown_case,
        run_warning_case,
        run_unchanged_case,
    ]

    reports: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []

    for case in cases:
        try:
            reports.append(case())
        except Exception as exc:
            failures.append(
                {
                    "case": case.__name__,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            )

    summary = {
        "phase": "3.2",
        "component": "deterministic_text_normalization",
        "total_cases": len(cases),
        "passed_cases": len(reports),
        "failed_cases": len(failures),
        "status": "passed" if not failures else "failed",
    }

    output = {
        "summary": summary,
        "cases": reports,
        "failures": failures,
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))

    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())