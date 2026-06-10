
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.providers.extraction.docx_extractor import DocxExtractor
from app.schemas.extraction import ExtractionInput
from app.schemas.source import SourceType


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse a local DOCX file using DocxExtractor.",
    )
    parser.add_argument(
        "file_path",
        type=Path,
        help="Path to the DOCX file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    file_path: Path = args.file_path

    if not file_path.is_file():
        raise SystemExit(f"File does not exist: {file_path}")

    if file_path.suffix.lower() != ".docx":
        raise SystemExit("The input file must have a .docx extension.")

    input_data = ExtractionInput(
        source_id="manual-test-source",
        document_id="manual-test-document",
        source_type=SourceType.docx,
        original_filename=file_path.name,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        content_bytes=file_path.read_bytes(),
    )

    result = DocxExtractor().extract(input_data)

    print(
        json.dumps(
            result.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()