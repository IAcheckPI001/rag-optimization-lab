def build_raw_unit_id(document_id: str, unit_index: int) -> str:
    stripped_document_id = document_id.strip()
    if not stripped_document_id:
        raise ValueError("document_id must not be blank")

    if unit_index < 0:
        raise ValueError("unit_index must be greater than or equal to 0")

    return f"raw:{stripped_document_id}:{unit_index:06d}"
