import pytest

from app.rag.cleaning.ids import build_clean_unit_id


def test_build_clean_unit_id_uses_raw_unit_index() -> None:
    clean_unit_id = build_clean_unit_id("document-001", 2)

    assert clean_unit_id == "clean:document-001:000002"


def test_build_clean_unit_id_strips_document_id() -> None:
    clean_unit_id = build_clean_unit_id("  document-001  ", 1)

    assert clean_unit_id == "clean:document-001:000001"


def test_build_clean_unit_id_is_deterministic() -> None:
    first = build_clean_unit_id("document-001", 42)
    second = build_clean_unit_id("document-001", 42)

    assert first == second


@pytest.mark.parametrize("document_id", ["", "   "])
def test_build_clean_unit_id_rejects_blank_document_id(document_id: str) -> None:
    with pytest.raises(ValueError, match="document_id must not be blank"):
        build_clean_unit_id(document_id, 0)


def test_build_clean_unit_id_rejects_negative_raw_unit_index() -> None:
    with pytest.raises(
        ValueError,
        match="raw_unit_index must be greater than or equal to 0",
    ):
        build_clean_unit_id("document-001", -1)
