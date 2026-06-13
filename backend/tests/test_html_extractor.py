import pytest

from app.providers.extraction.errors import (
    ExtractionNoContentError,
    ExtractionParsingError,
    ExtractionSourceTypeMismatchError,
)
from app.providers.extraction.html_extractor import HtmlExtractionPolicy, HtmlExtractor
from app.schemas.document import DocumentContentType
from app.schemas.extraction import ExtractionInput, ExtractionResult
from app.schemas.source import SourceType


def html_input(
    content: str | bytes,
    *,
    source_type: SourceType = SourceType.url,
    media_type: str | None = "text/html",
    charset: str | None = "utf-8",
    source_uri: str | None = "https://example.com/article",
) -> ExtractionInput:
    content_bytes = content if isinstance(content, bytes) else content.encode("utf-8")
    return ExtractionInput(
        source_id="src_001",
        document_id="doc_001",
        source_type=source_type,
        source_uri=source_uri,
        media_type=media_type,
        charset=charset,
        content_bytes=content_bytes,
    )


def extract(content: str, **kwargs) -> ExtractionResult:
    return HtmlExtractor(extractor_version="test-version").extract(
        html_input(content, **kwargs)
    )


def test_html_extractor_extracts_structural_units_in_dom_order() -> None:
    result = extract(
        """
        <html>
          <head><title>AI Guide</title></head>
          <body>
            <main>
              <h1>Overview</h1>
              <p>Line one<br>Line two&nbsp;now.</p>
              <ul><li>First item</li><li>Second item</li></ul>
              <table>
                <caption>Metrics</caption>
                <tr><th>Name</th><th>Value</th></tr>
                <tr><td>Accuracy</td><td>0.9</td></tr>
              </table>
              <pre><code>  x = 1\n  y = 2</code></pre>
            </main>
          </body>
        </html>
        """
    )

    assert result.extractor_name == "beautifulsoup4"
    assert result.extractor_version == "test-version"
    assert [unit.content for unit in result.units] == [
        "AI Guide",
        "Overview",
        "Line one\nLine two now.",
        "First item",
        "Second item",
        "Metrics",
        "Name\tValue\nAccuracy\t0.9",
        "  x = 1\n  y = 2",
    ]
    assert [unit.unit_index for unit in result.units] == list(range(8))
    assert [unit.raw_unit_id for unit in result.units] == [
        f"raw:doc_001:{index:06d}" for index in range(8)
    ]
    assert len({unit.extracted_at for unit in result.units}) == 1
    assert {unit.source_uri for unit in result.units} == {
        "https://example.com/article"
    }
    assert result.units[1].content_type is DocumentContentType.paragraph
    assert result.units[1].extra_metadata["block_type"] == "heading"
    assert result.units[1].extra_metadata["heading_level"] == 1
    assert result.units[2].heading_path == ["Overview"]
    assert result.units[2].section == "Overview"
    assert result.units[3].content_type is DocumentContentType.list
    assert result.units[5].extra_metadata["block_type"] == "table_caption"
    assert result.units[6].content_type is DocumentContentType.table
    assert result.units[6].extra_metadata["serialization_format"] == "tsv_escaped_v1"
    assert result.units[7].content_type is DocumentContentType.code
    assert result.stats.total_units == len(result.units)
    assert result.stats.warning_count == len(result.warnings)
    assert (
        result.stats.extra_metadata["observed_block_count"]
        == result.stats.total_units + result.stats.skipped_items
    )
    assert result.stats.extra_metadata["selected_root_strategy"] == "single_usable_main"


def test_html_extractor_rejects_source_type_mismatch() -> None:
    with pytest.raises(ExtractionSourceTypeMismatchError) as exc_info:
        HtmlExtractor(extractor_version="test-version").extract(
            html_input("<p>Mismatch</p>", source_type=SourceType.pdf)
        )

    assert exc_info.value.error_code == "extraction_source_type_mismatch"
    assert "content_bytes" not in exc_info.value.details


def test_html_extractor_validates_optional_media_type() -> None:
    with pytest.raises(ExtractionParsingError):
        HtmlExtractor(extractor_version="test-version").extract(
            html_input("<p>Nope</p>", media_type="application/pdf")
        )

    result = extract("<p>Allowed without media type.</p>", media_type=None)
    assert result.units[0].content == "Allowed without media type."


def test_html_extractor_invalid_declared_charset_warns_and_falls_back() -> None:
    result = extract(
        "<html><body><p>Tiếng Việt</p></body></html>",
        charset="not-a-codec",
    )

    assert len(result.warnings) == 1
    warning = result.warnings[0]
    assert warning.warning_code == "invalid_declared_charset"
    assert warning.extra_metadata["declared_charset"] == "not-a-codec"
    assert result.units[0].content == "Tiếng Việt"
    assert result.stats.extra_metadata["declared_charset"] == "not-a-codec"
    assert result.stats.extra_metadata["declared_charset_valid"] is False
    assert result.stats.extra_metadata["charset_fallback_used"] is True
    assert "declared_charset" not in result.units[0].extra_metadata


def test_html_extractor_heading_state_skips_blank_headings() -> None:
    result = extract(
        """
        <main>
          <h1>Top</h1>
          <h2>   </h2>
          <p>Body</p>
          <h2>Child</h2>
          <p>Nested body</p>
        </main>
        """
    )

    assert [unit.content for unit in result.units] == [
        "Top",
        "Body",
        "Child",
        "Nested body",
    ]
    assert result.units[1].heading_path == ["Top"]
    assert result.units[2].heading_path == ["Top", "Child"]
    assert result.units[3].section == "Child"
    assert result.stats.skipped_items == 1
    assert result.stats.extra_metadata["emitted_heading_count"] == 2


def test_html_extractor_root_selection_ignores_empty_main_and_body_boilerplate() -> None:
    result = extract(
        """
        <html>
          <body>
            <header><p>Login</p></header>
            <main>   </main>
            <article><p>Article body</p></article>
            <footer><p>Privacy</p></footer>
          </body>
        </html>
        """
    )

    assert [unit.content for unit in result.units] == ["Article body"]
    assert result.units[0].extra_metadata["block_index"] == 0
    assert result.stats.skipped_items == 0
    assert result.stats.extra_metadata["selected_root_strategy"] == (
        "single_usable_article"
    )
    assert result.stats.extra_metadata["ignored_semantic_container_count"] == 0


def test_html_extractor_body_fallback_ignores_page_level_semantic_containers() -> None:
    result = extract(
        """
        <body>
          <nav><ul><li>Home</li></ul></nav>
          <header><p>Login</p></header>
          <article><p>One</p></article>
          <article><p>Two</p></article>
          <footer><p>Privacy</p></footer>
        </body>
        """
    )

    assert [unit.content for unit in result.units] == ["One", "Two"]
    assert [unit.extra_metadata["block_index"] for unit in result.units] == [0, 1]
    assert result.stats.skipped_items == 0
    assert result.stats.extra_metadata["selected_root_strategy"] == "body_fallback"
    assert result.stats.extra_metadata["ignored_semantic_container_count"] == 3


def test_html_extractor_list_items_use_direct_owned_text_without_nested_duplication() -> None:
    result = extract(
        """
        <main>
          <ul>
            <li>
              <p>Install Python</p>
              <strong>before continuing</strong>
              <ul>
                <li>Create a venv</li>
              </ul>
            </li>
          </ul>
        </main>
        """
    )

    assert [unit.content for unit in result.units] == [
        "Install Python before continuing",
        "Create a venv",
    ]
    parent = result.units[0].extra_metadata
    child = result.units[1].extra_metadata
    assert parent["list_container_global_index"] == 0
    assert parent["list_item_global_index"] == 0
    assert parent["list_item_index_in_container"] == 0
    assert parent["list_depth"] == 0
    assert "parent_emitted_list_item_global_index" not in parent
    assert child["list_container_global_index"] == 1
    assert child["list_item_global_index"] == 1
    assert child["list_depth"] == 1
    assert child["parent_emitted_list_item_global_index"] == 0


def test_html_extractor_blank_parent_list_item_does_not_block_child_item() -> None:
    result = extract(
        """
        <main>
          <ul>
            <li>
              <ul><li>Child only</li></ul>
            </li>
          </ul>
        </main>
        """
    )

    assert [unit.content for unit in result.units] == ["Child only"]
    assert result.stats.skipped_items == 1
    assert result.units[0].extra_metadata["list_item_global_index"] == 1
    assert "parent_emitted_list_item_global_index" not in result.units[0].extra_metadata


def test_html_extractor_caption_and_table_are_separate_candidates() -> None:
    result = extract(
        """
        <main>
          <table>
            <caption>   </caption>
            <tr><td>A</td></tr>
          </table>
        </main>
        """
    )

    assert [unit.content for unit in result.units] == ["A"]
    assert result.units[0].extra_metadata["block_type"] == "table"
    assert result.units[0].extra_metadata["block_index"] == 1
    assert result.stats.skipped_items == 1
    assert result.stats.extra_metadata["observed_block_count"] == 2


def test_html_extractor_table_serialization_matches_docx_tsv_semantics() -> None:
    result = extract(
        r"""
        <main>
          <table>
            <tr>
              <th>A	B</th>
              <td>Line 1
Line 2</td>
              <td>C:\Docs</td>
            </tr>
            <tr><td>Only one cell</td></tr>
          </table>
        </main>
        """
    )

    unit = result.units[0]
    assert unit.content == r"A\tB	Line 1\nLine 2	C:\\Docs" + "\nOnly one cell"
    assert unit.extra_metadata["row_count"] == 2
    assert unit.extra_metadata["column_count"] == 3
    assert unit.extra_metadata["row_column_counts"] == [3, 1]


def test_html_extractor_nested_table_does_not_duplicate_or_pollute_counts() -> None:
    result = extract(
        """
        <main>
          <table>
            <tr>
              <td>Outer <table><tr><td>Inner</td></tr></table> Tail</td>
            </tr>
          </table>
        </main>
        """
    )

    unit = result.units[0]
    assert unit.content == "Outer Tail"
    assert unit.extra_metadata["row_count"] == 1
    assert unit.extra_metadata["column_count"] == 1
    assert unit.extra_metadata["row_column_counts"] == [1]
    assert result.stats.extra_metadata["nested_table_ignored_count"] == 1
    assert result.warnings == []


def test_html_extractor_blockquote_preserves_direct_text_and_child_dom_order() -> None:
    result = extract(
        """
        <main>
          <blockquote>
            Intro
            <p>Quoted paragraph</p>
            Outro
          </blockquote>
        </main>
        """
    )

    assert [unit.content for unit in result.units] == [
        "Intro",
        "Quoted paragraph",
        "Outro",
    ]
    assert [unit.extra_metadata["block_type"] for unit in result.units] == [
        "blockquote_text",
        "paragraph",
        "blockquote_text",
    ]
    assert result.units[1].extra_metadata["nearest_semantic_container"] == "blockquote"


def test_html_extractor_bare_code_is_inline_but_pre_code_is_code_unit() -> None:
    result = extract(
        """
        <main>
          <p>Use <code>pip install</code> here.</p>
          <pre><code>pip install package</code></pre>
        </main>
        """
    )

    assert [unit.content for unit in result.units] == [
        "Use pip install here.",
        "pip install package",
    ]
    assert result.units[0].content_type is DocumentContentType.paragraph
    assert result.units[1].content_type is DocumentContentType.code


def test_html_extractor_leaf_container_fallback_extracts_direct_text() -> None:
    result = extract("<html><body><div>Hello world</div></body></html>")

    assert [unit.content for unit in result.units] == ["Hello world"]
    assert result.units[0].extra_metadata["block_type"] == "container_text"


def test_html_extractor_non_content_tags_are_not_candidates() -> None:
    result = extract(
        """
        <main>
          <script><p>Hidden</p></script>
          <style>p { color: red; }</style>
          <template><p>Template</p></template>
          <noscript><p>No script</p></noscript>
          <p>Visible</p>
        </main>
        """
    )

    assert [unit.content for unit in result.units] == ["Visible"]
    assert result.units[0].extra_metadata["block_index"] == 0
    assert result.stats.skipped_items == 0
    assert result.stats.extra_metadata["removed_non_content_tag_count"] == 4


def test_html_extractor_raises_no_content_for_empty_html() -> None:
    with pytest.raises(ExtractionNoContentError) as exc_info:
        extract("<html><body><main>   </main></body></html>")

    assert exc_info.value.error_code == "extraction_no_content"
    assert "content_bytes" not in exc_info.value.details


def test_html_extractor_resource_limits_raise_parsing_error_without_partial_result() -> None:
    extractor = HtmlExtractor(
        extractor_version="test-version",
        policy=HtmlExtractionPolicy(max_input_bytes=100, max_units=1),
    )

    with pytest.raises(ExtractionParsingError) as exc_info:
        extractor.extract(html_input("<main><p>One</p><p>Two</p></main>"))

    assert exc_info.value.error_code == "extraction_parsing_failed"
    assert "content_bytes" not in exc_info.value.details


def test_html_extractor_input_size_limit_is_checked_before_parse() -> None:
    extractor = HtmlExtractor(
        extractor_version="test-version",
        policy=HtmlExtractionPolicy(max_input_bytes=5),
    )

    with pytest.raises(ExtractionParsingError):
        extractor.extract(html_input("<p>Too long</p>"))
