from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

from app.providers.extraction.html_extractor import HtmlExtractor
from app.providers.fetching.httpx_url_fetcher import HttpxUrlFetcher
from app.schemas.extraction import ExtractionInput
from app.schemas.source import SourceType


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch one public HTML URL with Phase 2.4 UrlFetcher, "
            "then parse it with Phase 2.5 HtmlExtractor."
        ),
    )
    parser.add_argument("url", help="Public HTTP/HTTPS URL to fetch and extract.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("html_extraction_output.json"),
        help="UTF-8 JSON output path.",
    )
    parser.add_argument(
        "--source-id",
        default="manual-url-test-source",
        help="Temporary source ID.",
    )
    parser.add_argument(
        "--document-id",
        default="manual-url-test-document",
        help="Temporary document ID.",
    )
    return parser.parse_args()


def infer_original_filename(url: str) -> str | None:
    path = unquote(urlsplit(url).path)
    filename = Path(path).name.strip()
    return filename or None


def build_extraction_input(
    fetched_content: object,
    source_id: str,
    document_id: str,
) -> ExtractionInput:
    model_fields = ExtractionInput.model_fields

    final_url = getattr(fetched_content, "final_url")
    media_type = getattr(fetched_content, "media_type", None)
    charset = getattr(fetched_content, "charset", None)
    content_bytes = getattr(fetched_content, "content_bytes")

    candidate_values: dict[str, object] = {
        "source_id": source_id,
        "document_id": document_id,
        "source_type": SourceType.url,
        "source_uri": final_url,
        "original_filename": infer_original_filename(final_url),
        "media_type": media_type,
        "content_mime": media_type,
        "charset": charset,
        "content_bytes": content_bytes,
        "created_at": datetime.now(timezone.utc),
        "extractor_config": {},
        "parser_config": {},
        "extra_metadata": {
            "fetch_original_url": getattr(fetched_content, "original_url", None),
            "fetch_final_url": final_url,
            "fetch_status_code": getattr(fetched_content, "status_code", None),
            "fetch_redirect_count": getattr(
                fetched_content,
                "redirect_count",
                None,
            ),
        },
    }

    payload = {
        field_name: candidate_values[field_name]
        for field_name in model_fields
        if field_name in candidate_values
    }
    return ExtractionInput(**payload)


def validate_result(result: object) -> list[str]:
    errors: list[str] = []
    units = list(getattr(result, "units"))
    warnings = list(getattr(result, "warnings"))
    stats = getattr(result, "stats")

    expected_indexes = list(range(len(units)))
    actual_indexes = [unit.unit_index for unit in units]
    if actual_indexes != expected_indexes:
        errors.append("unit_index is not continuous from zero.")

    raw_unit_ids = [unit.raw_unit_id for unit in units]
    if len(raw_unit_ids) != len(set(raw_unit_ids)):
        errors.append("raw_unit_id values are not unique.")

    if stats.total_units != len(units):
        errors.append("stats.total_units does not match len(units).")

    if stats.warning_count != len(warnings):
        errors.append("stats.warning_count does not match len(warnings).")

    timestamps = {unit.extracted_at for unit in units}
    if len(timestamps) > 1:
        errors.append("Units do not share one extraction timestamp.")

    source_uris = {unit.source_uri for unit in units}
    if len(source_uris) > 1:
        errors.append("Units do not share one source_uri.")

    extra_stats = getattr(stats, "extra_metadata", {}) or {}
    observed = extra_stats.get("observed_block_count")
    if observed is not None:
        expected_observed = stats.total_units + stats.skipped_items
        if observed != expected_observed:
            errors.append(
                "observed_block_count != total_units + skipped_items."
            )

    return errors


def build_summary(fetched_content: object, extraction_result: object) -> dict[str, object]:
    units = list(getattr(extraction_result, "units"))
    stats = getattr(extraction_result, "stats")

    content_types = Counter(
        str(getattr(unit.content_type, "value", unit.content_type))
        for unit in units
    )
    block_types = Counter(
        str(unit.extra_metadata.get("block_type", "unknown"))
        for unit in units
    )

    return {
        "fetch": {
            "original_url": getattr(fetched_content, "original_url", None),
            "final_url": getattr(fetched_content, "final_url", None),
            "status_code": getattr(fetched_content, "status_code", None),
            "redirect_count": getattr(fetched_content, "redirect_count", None),
            "media_type": getattr(fetched_content, "media_type", None),
            "charset": getattr(fetched_content, "charset", None),
            "downloaded_bytes": (
                getattr(fetched_content, "extra_metadata", {}) or {}
            ).get("downloaded_bytes"),
        },
        "extraction": {
            "total_units": stats.total_units,
            "skipped_items": stats.skipped_items,
            "warning_count": stats.warning_count,
            "content_types": dict(content_types),
            "block_types": dict(block_types),
            "stats_extra_metadata": stats.extra_metadata,
        },
    }


def main() -> None:
    args = parse_args()

    fetched_content = HttpxUrlFetcher().fetch(args.url)
    extraction_input = build_extraction_input(
        fetched_content,
        args.source_id,
        args.document_id,
    )
    extraction_result = HtmlExtractor().extract(extraction_input)

    validation_errors = validate_result(extraction_result)
    if validation_errors:
        details = "\n".join(f"- {item}" for item in validation_errors)
        raise SystemExit(f"Smoke-test validation failed:\n{details}")

    payload = {
        "summary": build_summary(fetched_content, extraction_result),
        "fetched_content": fetched_content.model_dump(mode="json"),
        "extraction_result": extraction_result.model_dump(mode="json"),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary = payload["summary"]
    print("Smoke test completed successfully.")
    print(f"Original URL: {summary['fetch']['original_url']}")
    print(f"Final URL:    {summary['fetch']['final_url']}")
    print(f"HTTP status:  {summary['fetch']['status_code']}")
    print(f"Redirects:    {summary['fetch']['redirect_count']}")
    print(f"Downloaded:   {summary['fetch']['downloaded_bytes']} bytes")
    print(f"Units:        {summary['extraction']['total_units']}")
    print(f"Skipped:      {summary['extraction']['skipped_items']}")
    print(f"Warnings:     {summary['extraction']['warning_count']}")
    print(f"Output:       {args.output.resolve()}")


if __name__ == "__main__":
    main()
