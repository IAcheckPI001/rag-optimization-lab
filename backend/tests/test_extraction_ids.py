import pytest

from app.providers.extraction.ids import build_raw_unit_id


def test_build_raw_unit_id_formats_zero_padded_unit_index() -> None:
    assert build_raw_unit_id("doc_123", 0) == "raw:doc_123:000000"
    assert build_raw_unit_id("doc_123", 12) == "raw:doc_123:000012"


def test_build_raw_unit_id_strips_document_id() -> None:
    assert build_raw_unit_id("  doc_123  ", 1) == "raw:doc_123:000001"


@pytest.mark.parametrize("document_id", ["", "   "])
def test_build_raw_unit_id_rejects_blank_document_id(document_id: str) -> None:
    with pytest.raises(ValueError, match="document_id must not be blank"):
        build_raw_unit_id(document_id, 0)


def test_build_raw_unit_id_rejects_negative_unit_index() -> None:
    with pytest.raises(ValueError, match="unit_index must be greater"):
        build_raw_unit_id("doc_123", -1)


def test_build_raw_unit_id_is_deterministic() -> None:
    first = build_raw_unit_id("doc_123", 4)
    second = build_raw_unit_id("doc_123", 4)

    assert first == second
