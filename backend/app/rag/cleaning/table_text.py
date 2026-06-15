from __future__ import annotations


TSV_ESCAPED_V1 = "tsv_escaped_v1"


def parse_tsv_escaped_v1(content: str) -> list[list[str]]:
    return [
        [_unescape_cell(cell) for cell in row.split("\t")]
        for row in content.split("\n")
    ]


def serialize_tsv_escaped_v1(rows: list[list[str]]) -> str:
    return "\n".join("\t".join(_escape_cell(cell) for cell in row) for row in rows)


def _escape_cell(cell_text: str) -> str:
    return (
        cell_text.replace("\\", "\\\\")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\t", "\\t")
        .replace("\n", "\\n")
    )


def _unescape_cell(cell_text: str) -> str:
    pieces: list[str] = []
    index = 0

    while index < len(cell_text):
        character = cell_text[index]
        if character != "\\":
            pieces.append(character)
            index += 1
            continue

        if index + 1 >= len(cell_text):
            pieces.append("\\")
            index += 1
            continue

        escaped = cell_text[index + 1]
        if escaped == "\\":
            pieces.append("\\")
        elif escaped == "t":
            pieces.append("\t")
        elif escaped == "n":
            pieces.append("\n")
        else:
            pieces.append("\\")
            pieces.append(escaped)
        index += 2

    return "".join(pieces)
