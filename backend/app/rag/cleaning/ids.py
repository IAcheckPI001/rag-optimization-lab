def build_clean_unit_id(document_id: str, raw_unit_index: int) -> str:
    stripped_document_id = document_id.strip()
    if not stripped_document_id:
        raise ValueError("document_id must not be blank")

    if raw_unit_index < 0:
        raise ValueError("raw_unit_index must be greater than or equal to 0")

    return f"clean:{stripped_document_id}:{raw_unit_index:06d}"
