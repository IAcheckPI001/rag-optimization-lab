
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.providers.extraction.pdf_extractor import PdfExtractor
from app.schemas.extraction import ExtractionInput
from app.schemas.source import SourceType


PDF_MEDIA_TYPE = "application/pdf"


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse a local PDF file using PdfExtractor.",
    )

    parser.add_argument(
        "file_path",
        type=Path,
        help="Path to the PDF file.",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional UTF-8 JSON output path.",
    )

    parser.add_argument(
        "--source-uri",
        default=None,
        help="Optional stable source URI for provenance testing.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    file_path: Path = args.file_path

    if not file_path.is_file():
        raise SystemExit(f"File does not exist: {file_path}")

    if file_path.suffix.lower() != ".pdf":
        raise SystemExit("The input file must have a .pdf extension.")

    input_data = ExtractionInput(
        source_id="manual-pdf-test-source",
        document_id="manual-pdf-test-document",
        source_type=SourceType.pdf,
        source_uri=args.source_uri,
        original_filename=file_path.name,
        media_type=PDF_MEDIA_TYPE,
        content_bytes=file_path.read_bytes(),
    )

    result = PdfExtractor().extract(input_data)

    payload = json.dumps(
        result.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
    )

    if args.output is not None:
        args.output.write_text(
            payload,
            encoding="utf-8",
        )
        print(f"Output written to: {args.output.resolve()}")
    else:
        print(payload)


if __name__ == "__main__":
    main()