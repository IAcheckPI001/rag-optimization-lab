from __future__ import annotations

import codecs
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError as MetadataPackageNotFoundError
from importlib.metadata import version
import re

from bs4 import BeautifulSoup
from bs4 import NavigableString
from bs4 import Tag
from bs4.builder import ParserRejectedMarkup
from pydantic import ValidationError

from app.providers.extraction.errors import (
    ExtractionInvariantError,
    ExtractionNoContentError,
    ExtractionParsingError,
    ExtractionSourceTypeMismatchError,
)
from app.providers.extraction.ids import build_raw_unit_id
from app.schemas.document import DocumentContentType, RawDocumentUnit
from app.schemas.extraction import (
    ExtractionInput,
    ExtractionResult,
    ExtractionStats,
    ExtractionWarning,
)
from app.schemas.source import ProcessingStage, SourceType


TABLE_SERIALIZATION_FORMAT = "tsv_escaped_v1"
SUPPORTED_MEDIA_TYPES = {"text/html", "application/xhtml+xml"}
NON_CONTENT_TAGS = {"script", "style", "template", "noscript"}
IGNORED_BODY_CONTAINERS = {"nav", "header", "footer", "aside"}
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
FALLBACK_CONTAINER_TAGS = {"div", "section", "article"}
ROW_GROUP_TAGS = {"thead", "tbody", "tfoot"}
HORIZONTAL_WHITESPACE_PATTERN = re.compile(r"[^\S\n]+")
TABLE_CELL_SPACE_PATTERN = re.compile(r"[ \f\v]+")
BLANK_LINE_EDGE_PATTERN = re.compile(r"^\s*\n|\n\s*$")


@dataclass(frozen=True)
class HtmlExtractionPolicy:
    max_input_bytes: int = 5 * 1024 * 1024
    max_candidate_blocks: int = 50_000
    max_units: int = 10_000
    max_total_extracted_characters: int = 5_000_000


@dataclass
class _ExtractionState:
    input_data: ExtractionInput
    extractor_name: str
    extractor_version: str
    extracted_at: datetime
    policy: HtmlExtractionPolicy
    warnings: list[ExtractionWarning]
    units: list[RawDocumentUnit] = field(default_factory=list)
    heading_state: dict[int, str] = field(default_factory=dict)
    observed_block_count: int = 0
    skipped_items: int = 0
    total_extracted_characters: int = 0
    heading_index: int = 0
    paragraph_index: int = 0
    table_index: int = 0
    code_block_index: int = 0
    list_container_global_index: int = 0
    list_item_global_index: int = 0
    emitted_title_count: int = 0
    emitted_heading_count: int = 0
    emitted_paragraph_count: int = 0
    emitted_list_item_count: int = 0
    emitted_caption_count: int = 0
    emitted_table_count: int = 0
    emitted_code_block_count: int = 0
    emitted_blockquote_text_count: int = 0
    emitted_container_text_count: int = 0
    removed_non_content_tag_count: int = 0
    ignored_semantic_container_count: int = 0
    nested_table_ignored_count: int = 0
    selected_root_tag: str | None = None
    selected_root_strategy: str = "document_root"
    declared_charset: str | None = None
    declared_charset_valid: bool | None = None
    detected_encoding: str | None = None
    charset_fallback_used: bool = False


@dataclass(frozen=True)
class _SerializedTable:
    content: str
    row_count: int
    column_count: int
    row_column_counts: list[int]
    is_blank: bool
    nested_table_count: int


class HtmlExtractor:
    source_type = SourceType.url
    extractor_name = "beautifulsoup4"

    def __init__(
        self,
        extractor_version: str | None = None,
        policy: HtmlExtractionPolicy | None = None,
    ) -> None:
        self.extractor_version = extractor_version or _get_beautifulsoup_version()
        self.policy = policy or HtmlExtractionPolicy()

    def extract(self, input_data: ExtractionInput) -> ExtractionResult:
        if input_data.source_type is not SourceType.url:
            raise ExtractionSourceTypeMismatchError(
                "HtmlExtractor requires source_type=url.",
                details=_safe_input_details(input_data),
            )

        _validate_media_type(input_data)
        self._validate_input_size(input_data)

        warnings: list[ExtractionWarning] = []
        soup, charset_valid, charset_fallback_used = self._parse_html(
            input_data, warnings
        )

        state = _ExtractionState(
            input_data=input_data,
            extractor_name=self.extractor_name,
            extractor_version=self.extractor_version,
            extracted_at=datetime.now(timezone.utc),
            policy=self.policy,
            warnings=warnings,
            declared_charset=input_data.charset,
            declared_charset_valid=charset_valid,
            detected_encoding=getattr(soup, "original_encoding", None),
            charset_fallback_used=charset_fallback_used,
        )

        state.removed_non_content_tag_count = _remove_non_content_tags(soup)
        root = _select_root(soup, state)

        title = _first_nonblank_title(soup)
        if title is not None:
            self._emit_text_candidate(
                state=state,
                content=title,
                content_type=DocumentContentType.paragraph,
                block_type="document_title",
                html_tag="title",
                extra_metadata={},
                update_heading_level=None,
            )
            state.emitted_title_count += 1

        self._process_children(root, state)

        if not state.units:
            raise ExtractionNoContentError(
                "HTML content contains no extractable units.",
                details={
                    **_safe_input_details(input_data),
                    "observed_block_count": state.observed_block_count,
                    "skipped_items": state.skipped_items,
                    "selected_root_tag": state.selected_root_tag,
                    "selected_root_strategy": state.selected_root_strategy,
                },
            )

        stats = ExtractionStats(
            total_units=len(state.units),
            skipped_items=state.skipped_items,
            warning_count=len(state.warnings),
            extra_metadata={
                "selected_root_tag": state.selected_root_tag,
                "selected_root_strategy": state.selected_root_strategy,
                "declared_charset": state.declared_charset,
                "declared_charset_valid": state.declared_charset_valid,
                "detected_encoding": state.detected_encoding,
                "charset_fallback_used": state.charset_fallback_used,
                "removed_non_content_tag_count": state.removed_non_content_tag_count,
                "ignored_semantic_container_count": (
                    state.ignored_semantic_container_count
                ),
                "nested_table_ignored_count": state.nested_table_ignored_count,
                "observed_block_count": state.observed_block_count,
                "emitted_title_count": state.emitted_title_count,
                "emitted_heading_count": state.emitted_heading_count,
                "emitted_paragraph_count": state.emitted_paragraph_count,
                "emitted_list_item_count": state.emitted_list_item_count,
                "emitted_caption_count": state.emitted_caption_count,
                "emitted_table_count": state.emitted_table_count,
                "emitted_code_block_count": state.emitted_code_block_count,
                "emitted_blockquote_text_count": (
                    state.emitted_blockquote_text_count
                ),
                "emitted_container_text_count": state.emitted_container_text_count,
            },
        )

        try:
            return ExtractionResult(
                source_id=input_data.source_id,
                document_id=input_data.document_id,
                source_type=SourceType.url,
                extractor_name=self.extractor_name,
                extractor_version=self.extractor_version,
                units=state.units,
                warnings=state.warnings,
                stats=stats,
            )
        except ValidationError as exc:
            raise ExtractionInvariantError(
                "HTML extractor produced an invalid ExtractionResult.",
                details={
                    "source_id": input_data.source_id,
                    "document_id": input_data.document_id,
                    "unit_count": len(state.units),
                    "warning_count": len(state.warnings),
                },
            ) from exc

    def _validate_input_size(self, input_data: ExtractionInput) -> None:
        if len(input_data.content_bytes) > self.policy.max_input_bytes:
            raise ExtractionParsingError(
                "HTML content exceeds extractor input size limit.",
                details={
                    **_safe_input_details(input_data),
                    "content_length": len(input_data.content_bytes),
                    "max_input_bytes": self.policy.max_input_bytes,
                },
            )

    def _parse_html(
        self,
        input_data: ExtractionInput,
        warnings: list[ExtractionWarning],
    ) -> tuple[BeautifulSoup, bool | None, bool]:
        charset_valid: bool | None = None
        charset_fallback_used = False
        from_encoding = input_data.charset

        if input_data.charset is not None:
            try:
                codecs.lookup(input_data.charset)
                charset_valid = True
            except LookupError:
                charset_valid = False
                charset_fallback_used = True
                from_encoding = None
                warnings.append(
                    ExtractionWarning(
                        warning_code="invalid_declared_charset",
                        message="Declared HTML charset is invalid; parser detection was used.",
                        stage=ProcessingStage.parsing,
                        extra_metadata={
                            "parser": self.extractor_name,
                            "parser_version": self.extractor_version,
                            "declared_charset": input_data.charset,
                        },
                    )
                )

        try:
            return (
                BeautifulSoup(
                    input_data.content_bytes,
                    "html.parser",
                    from_encoding=from_encoding,
                ),
                charset_valid,
                charset_fallback_used,
            )
        except (ParserRejectedMarkup, UnicodeDecodeError) as exc:
            raise ExtractionParsingError(
                "Unable to parse HTML content.",
                details=_safe_input_details(input_data),
            ) from exc

    def _process_children(
        self,
        parent: Tag | BeautifulSoup,
        state: _ExtractionState,
        *,
        nearest_semantic_container: str | None = None,
    ) -> None:
        for child in list(parent.children):
            if isinstance(child, NavigableString):
                continue
            if not isinstance(child, Tag):
                continue
            if _is_non_content_tag(child):
                continue
            if _should_ignore_body_container(child, state):
                state.ignored_semantic_container_count += 1
                continue
            self._process_tag(
                child,
                state,
                nearest_semantic_container=nearest_semantic_container,
            )

    def _process_tag(
        self,
        tag: Tag,
        state: _ExtractionState,
        *,
        nearest_semantic_container: str | None = None,
    ) -> None:
        name = _tag_name(tag)

        if name in HEADING_TAGS:
            self._process_heading(tag, state, nearest_semantic_container)
            return
        if name == "p":
            self._process_paragraph(tag, state, nearest_semantic_container)
            return
        if name == "pre":
            self._process_code_block(tag, state, nearest_semantic_container)
            return
        if name == "table":
            self._process_table(tag, state, nearest_semantic_container)
            return
        if name == "blockquote":
            self._process_blockquote(tag, state)
            return
        if name in {"ul", "ol"}:
            self._process_list(
                tag,
                state,
                list_depth=0,
                parent_emitted_list_item_global_index=None,
                nearest_semantic_container=nearest_semantic_container,
            )
            return
        if name in FALLBACK_CONTAINER_TAGS and _is_leaf_fallback_container(tag):
            content = _serialize_structural_text(tag)
            self._emit_text_candidate(
                state=state,
                content=content,
                content_type=DocumentContentType.paragraph,
                block_type="container_text",
                html_tag=name,
                extra_metadata={
                    "nearest_semantic_container": nearest_semantic_container
                },
                update_heading_level=None,
            )
            state.emitted_container_text_count += int(bool(content.strip()))
            return

        self._process_children(
            tag,
            state,
            nearest_semantic_container=nearest_semantic_container,
        )

    def _process_heading(
        self,
        tag: Tag,
        state: _ExtractionState,
        nearest_semantic_container: str | None,
    ) -> None:
        heading_level = int(_tag_name(tag)[1:])
        current_heading_index = state.heading_index
        state.heading_index += 1
        content = _serialize_structural_text(tag)
        emitted = self._emit_text_candidate(
            state=state,
            content=content,
            content_type=DocumentContentType.paragraph,
            block_type="heading",
            html_tag=_tag_name(tag),
            extra_metadata={
                "heading_level": heading_level,
                "heading_index": current_heading_index,
                "nearest_semantic_container": nearest_semantic_container,
            },
            update_heading_level=heading_level,
        )
        if emitted:
            state.emitted_heading_count += 1

    def _process_paragraph(
        self,
        tag: Tag,
        state: _ExtractionState,
        nearest_semantic_container: str | None,
    ) -> None:
        current_paragraph_index = state.paragraph_index
        state.paragraph_index += 1
        content = _serialize_structural_text(tag)
        emitted = self._emit_text_candidate(
            state=state,
            content=content,
            content_type=DocumentContentType.paragraph,
            block_type="paragraph",
            html_tag="p",
            extra_metadata={
                "paragraph_index": current_paragraph_index,
                "nearest_semantic_container": nearest_semantic_container,
            },
            update_heading_level=None,
        )
        if emitted:
            state.emitted_paragraph_count += 1

    def _process_code_block(
        self,
        tag: Tag,
        state: _ExtractionState,
        nearest_semantic_container: str | None,
    ) -> None:
        current_code_block_index = state.code_block_index
        state.code_block_index += 1
        content = _serialize_preformatted_text(tag)
        emitted = self._emit_text_candidate(
            state=state,
            content=content,
            content_type=DocumentContentType.code,
            block_type="code_block",
            html_tag="pre",
            extra_metadata={
                "code_block_index": current_code_block_index,
                "nearest_semantic_container": nearest_semantic_container,
            },
            update_heading_level=None,
        )
        if emitted:
            state.emitted_code_block_count += 1

    def _process_list(
        self,
        tag: Tag,
        state: _ExtractionState,
        *,
        list_depth: int,
        parent_emitted_list_item_global_index: int | None,
        nearest_semantic_container: str | None,
    ) -> None:
        list_container_global_index = state.list_container_global_index
        state.list_container_global_index += 1
        list_type = "ordered" if _tag_name(tag) == "ol" else "unordered"

        direct_items = [
            child
            for child in tag.children
            if isinstance(child, Tag) and _tag_name(child) == "li"
        ]
        for list_item_index_in_container, item in enumerate(direct_items):
            list_item_global_index = state.list_item_global_index
            state.list_item_global_index += 1
            content = _serialize_list_item_text(item)
            emitted = self._emit_text_candidate(
                state=state,
                content=content,
                content_type=DocumentContentType.list,
                block_type="list_item",
                html_tag="li",
                extra_metadata={
                    "list_container_global_index": list_container_global_index,
                    "list_item_global_index": list_item_global_index,
                    "list_item_index_in_container": list_item_index_in_container,
                    "list_depth": list_depth,
                    "list_type": list_type,
                    "parent_emitted_list_item_global_index": (
                        parent_emitted_list_item_global_index
                    ),
                    "nearest_semantic_container": nearest_semantic_container,
                },
                update_heading_level=None,
            )
            emitted_parent_index = list_item_global_index if emitted else None
            if emitted:
                state.emitted_list_item_count += 1

            for nested_list in _direct_child_tags(item, {"ul", "ol"}):
                self._process_list(
                    nested_list,
                    state,
                    list_depth=list_depth + 1,
                    parent_emitted_list_item_global_index=emitted_parent_index,
                    nearest_semantic_container=nearest_semantic_container,
                )

    def _process_table(
        self,
        tag: Tag,
        state: _ExtractionState,
        nearest_semantic_container: str | None,
    ) -> None:
        caption = _direct_child_tag(tag, "caption")
        if caption is not None:
            content = _serialize_structural_text(caption)
            emitted = self._emit_text_candidate(
                state=state,
                content=content,
                content_type=DocumentContentType.paragraph,
                block_type="table_caption",
                html_tag="caption",
                extra_metadata={
                    "table_index": state.table_index,
                    "nearest_semantic_container": nearest_semantic_container,
                },
                update_heading_level=None,
            )
            if emitted:
                state.emitted_caption_count += 1

        current_table_index = state.table_index
        state.table_index += 1
        table_data = _serialize_table(tag)
        state.nested_table_ignored_count += table_data.nested_table_count
        emitted = self._emit_text_candidate(
            state=state,
            content=table_data.content,
            content_type=DocumentContentType.table,
            block_type="table",
            html_tag="table",
            extra_metadata={
                "table_index": current_table_index,
                "row_count": table_data.row_count,
                "column_count": table_data.column_count,
                "row_column_counts": table_data.row_column_counts,
                "serialization_format": TABLE_SERIALIZATION_FORMAT,
                "nearest_semantic_container": nearest_semantic_container,
            },
            update_heading_level=None,
            force_blank=table_data.is_blank,
        )
        if emitted:
            state.emitted_table_count += 1

    def _process_blockquote(self, tag: Tag, state: _ExtractionState) -> None:
        if not _has_recognized_descendant(tag):
            content = _serialize_structural_text(tag)
            emitted = self._emit_text_candidate(
                state=state,
                content=content,
                content_type=DocumentContentType.paragraph,
                block_type="blockquote",
                html_tag="blockquote",
                extra_metadata={},
                update_heading_level=None,
            )
            if emitted:
                state.emitted_blockquote_text_count += 1
            return

        for child in list(tag.children):
            if isinstance(child, NavigableString):
                content = _normalize_structural_text(str(child))
                if content:
                    emitted = self._emit_text_candidate(
                        state=state,
                        content=content,
                        content_type=DocumentContentType.paragraph,
                        block_type="blockquote_text",
                        html_tag="blockquote",
                        extra_metadata={
                            "nearest_semantic_container": "blockquote"
                        },
                        update_heading_level=None,
                    )
                    if emitted:
                        state.emitted_blockquote_text_count += 1
                continue
            if not isinstance(child, Tag):
                continue
            if _is_non_content_tag(child):
                continue
            if _tag_name(child) in FALLBACK_CONTAINER_TAGS and _is_leaf_fallback_container(
                child
            ):
                content = _serialize_structural_text(child)
                emitted = self._emit_text_candidate(
                    state=state,
                    content=content,
                    content_type=DocumentContentType.paragraph,
                    block_type="blockquote_text",
                    html_tag=_tag_name(child),
                    extra_metadata={
                        "nearest_semantic_container": "blockquote"
                    },
                    update_heading_level=None,
                )
                if emitted:
                    state.emitted_blockquote_text_count += 1
                continue
            self._process_tag(
                child,
                state,
                nearest_semantic_container="blockquote",
            )

    def _emit_text_candidate(
        self,
        *,
        state: _ExtractionState,
        content: str,
        content_type: DocumentContentType,
        block_type: str,
        html_tag: str,
        extra_metadata: dict[str, object],
        update_heading_level: int | None,
        force_blank: bool = False,
    ) -> bool:
        block_index = self._next_block_index(state)

        if force_blank or not content.strip():
            state.skipped_items += 1
            return False

        if update_heading_level is not None:
            state.heading_state[update_heading_level] = content
            state.heading_state = {
                level: text
                for level, text in state.heading_state.items()
                if level <= update_heading_level
            }

        self._ensure_can_emit_unit(state, content)
        heading_path = _heading_path(state.heading_state)
        metadata = {
            "parser": state.extractor_name,
            "parser_version": state.extractor_version,
            "block_type": block_type,
            "block_index": block_index,
            "html_tag": html_tag,
        }
        metadata.update(
            {
                key: value
                for key, value in extra_metadata.items()
                if value is not None
            }
        )

        unit_index = len(state.units)
        state.units.append(
            RawDocumentUnit(
                document_id=state.input_data.document_id,
                source_id=state.input_data.source_id,
                source_type=SourceType.url,
                source_uri=state.input_data.source_uri,
                content=content,
                page_start=None,
                page_end=None,
                section=heading_path[-1] if heading_path else None,
                heading_path=heading_path,
                content_type=content_type,
                extra_metadata=metadata,
                raw_unit_id=build_raw_unit_id(
                    state.input_data.document_id, unit_index
                ),
                unit_index=unit_index,
                extracted_at=state.extracted_at,
            )
        )
        state.total_extracted_characters += len(content)
        return True

    def _next_block_index(self, state: _ExtractionState) -> int:
        if state.observed_block_count >= state.policy.max_candidate_blocks:
            raise ExtractionParsingError(
                "HTML candidate block limit exceeded.",
                details={
                    **_safe_input_details(state.input_data),
                    "max_candidate_blocks": state.policy.max_candidate_blocks,
                },
            )
        block_index = state.observed_block_count
        state.observed_block_count += 1
        return block_index

    def _ensure_can_emit_unit(self, state: _ExtractionState, content: str) -> None:
        if len(state.units) >= state.policy.max_units:
            raise ExtractionParsingError(
                "HTML extracted unit limit exceeded.",
                details={
                    **_safe_input_details(state.input_data),
                    "max_units": state.policy.max_units,
                },
            )

        next_character_total = state.total_extracted_characters + len(content)
        if next_character_total > state.policy.max_total_extracted_characters:
            raise ExtractionParsingError(
                "HTML extracted character limit exceeded.",
                details={
                    **_safe_input_details(state.input_data),
                    "max_total_extracted_characters": (
                        state.policy.max_total_extracted_characters
                    ),
                },
            )


def _get_beautifulsoup_version() -> str:
    try:
        return version("beautifulsoup4")
    except MetadataPackageNotFoundError as exc:
        raise ExtractionInvariantError(
            "BeautifulSoup package metadata is unavailable.",
            details={"package_name": "beautifulsoup4"},
        ) from exc


def _safe_input_details(input_data: ExtractionInput) -> dict[str, object]:
    details: dict[str, object] = {
        "source_id": input_data.source_id,
        "document_id": input_data.document_id,
        "source_type": input_data.source_type.value,
    }
    if input_data.source_uri:
        details["source_uri"] = input_data.source_uri
    if input_data.original_filename:
        details["original_filename"] = input_data.original_filename
    if input_data.media_type:
        details["media_type"] = input_data.media_type
    return details


def _validate_media_type(input_data: ExtractionInput) -> None:
    if input_data.media_type is None:
        return

    media_type = input_data.media_type.split(";", 1)[0].strip().lower()
    if media_type not in SUPPORTED_MEDIA_TYPES:
        raise ExtractionParsingError(
            "Unsupported HTML media type.",
            details=_safe_input_details(input_data),
        )


def _remove_non_content_tags(soup: BeautifulSoup) -> int:
    tags = soup.find_all(NON_CONTENT_TAGS)
    for tag in tags:
        tag.decompose()
    return len(tags)


def _select_root(soup: BeautifulSoup, state: _ExtractionState) -> Tag | BeautifulSoup:
    usable_mains = [
        tag for tag in soup.find_all("main") if _is_usable_root(tag)
    ]
    if len(usable_mains) == 1:
        state.selected_root_tag = "main"
        state.selected_root_strategy = "single_usable_main"
        return usable_mains[0]

    usable_articles = [
        tag for tag in soup.find_all("article") if _is_usable_root(tag)
    ]
    if len(usable_articles) == 1:
        state.selected_root_tag = "article"
        state.selected_root_strategy = "single_usable_article"
        return usable_articles[0]

    body = soup.body
    if body is not None:
        state.selected_root_tag = "body"
        state.selected_root_strategy = "body_fallback"
        return body

    state.selected_root_tag = "[document]"
    state.selected_root_strategy = "document_root"
    return soup


def _is_usable_root(tag: Tag) -> bool:
    return bool(_serialize_structural_text(tag).strip())


def _first_nonblank_title(soup: BeautifulSoup) -> str | None:
    title = soup.find("title")
    if title is None:
        return None
    content = _serialize_structural_text(title)
    if content.strip():
        return content
    return None


def _is_non_content_tag(tag: Tag) -> bool:
    return _tag_name(tag) in NON_CONTENT_TAGS


def _should_ignore_body_container(tag: Tag, state: _ExtractionState) -> bool:
    if state.selected_root_strategy != "body_fallback":
        return False
    if _tag_name(tag) not in IGNORED_BODY_CONTAINERS:
        return False
    return tag.find_parent(["main", "article"]) is None


def _tag_name(tag: Tag) -> str:
    return str(tag.name).lower()


def _heading_path(heading_state: dict[int, str]) -> list[str]:
    return [heading_state[level] for level in sorted(heading_state)]


def _direct_child_tags(parent: Tag, names: set[str]) -> list[Tag]:
    return [
        child
        for child in parent.children
        if isinstance(child, Tag) and _tag_name(child) in names
    ]


def _direct_child_tag(parent: Tag, name: str) -> Tag | None:
    for child in parent.children:
        if isinstance(child, Tag) and _tag_name(child) == name:
            return child
    return None


def _serialize_structural_text(
    tag: Tag | BeautifulSoup,
    *,
    exclude_tags: set[str] | None = None,
) -> str:
    raw_text = _collect_text(tag, exclude_tags=exclude_tags or set())
    return _normalize_structural_text(raw_text)


def _serialize_preformatted_text(tag: Tag) -> str:
    text = tag.get_text()
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    return BLANK_LINE_EDGE_PATTERN.sub("", text)


def _serialize_list_item_text(tag: Tag) -> str:
    text = _serialize_structural_text(tag, exclude_tags={"ul", "ol"})
    return _normalize_structural_text(text.replace("\n", " "))


def _collect_text(
    node: Tag | BeautifulSoup | NavigableString,
    *,
    exclude_tags: set[str],
    is_root: bool = True,
) -> str:
    if isinstance(node, NavigableString):
        return str(node)
    if not isinstance(node, (Tag, BeautifulSoup)):
        return ""
    if not is_root and isinstance(node, Tag) and _tag_name(node) in exclude_tags:
        return ""
    if isinstance(node, Tag) and _tag_name(node) == "br":
        return "\n"

    parts: list[str] = []
    for child in node.children:
        parts.append(_collect_text(child, exclude_tags=exclude_tags, is_root=False))
    return "".join(parts)


def _normalize_structural_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    lines = [
        HORIZONTAL_WHITESPACE_PATTERN.sub(" ", line).strip()
        for line in text.split("\n")
    ]
    collapsed: list[str] = []
    previous_blank = False
    for line in lines:
        if not line:
            if not previous_blank:
                collapsed.append("")
            previous_blank = True
            continue
        collapsed.append(line)
        previous_blank = False
    return "\n".join(collapsed).strip()


def _is_leaf_fallback_container(tag: Tag) -> bool:
    if not _direct_visible_text(tag).strip():
        return False
    for descendant in tag.descendants:
        if not isinstance(descendant, Tag):
            continue
        if descendant is tag:
            continue
        name = _tag_name(descendant)
        if name in HEADING_TAGS | {"p", "li", "table", "pre", "blockquote"}:
            return False
    return True


def _direct_visible_text(tag: Tag) -> str:
    parts: list[str] = []
    for child in tag.children:
        if isinstance(child, NavigableString):
            parts.append(str(child))
            continue
        if isinstance(child, Tag) and _tag_name(child) == "br":
            parts.append("\n")
    return _normalize_structural_text("".join(parts))


def _has_recognized_descendant(tag: Tag) -> bool:
    for descendant in tag.descendants:
        if not isinstance(descendant, Tag):
            continue
        if descendant is tag:
            continue
        name = _tag_name(descendant)
        if name in HEADING_TAGS | {"p", "li", "table", "pre", "blockquote"}:
            return True
    return False


def _serialize_table(table: Tag) -> _SerializedTable:
    rows: list[list[str]] = []
    raw_cell_texts: list[str] = []
    row_column_counts: list[int] = []
    nested_table_count = len(table.find_all("table"))

    for row in _direct_table_rows(table):
        cells = _direct_row_cells(row)
        row_column_counts.append(len(cells))
        row_values: list[str] = []
        for cell in cells:
            cell_text = _serialize_table_cell_text(cell)
            raw_cell_texts.append(cell_text)
            row_values.append(_escape_tsv_cell(cell_text))
        rows.append(row_values)

    is_blank = all(not cell_text.strip() for cell_text in raw_cell_texts)
    serialized_rows = ["\t".join(row) for row in rows]

    return _SerializedTable(
        content="\n".join(serialized_rows),
        row_count=len(rows),
        column_count=max(row_column_counts, default=0),
        row_column_counts=row_column_counts,
        is_blank=is_blank,
        nested_table_count=nested_table_count,
    )


def _direct_table_rows(table: Tag) -> list[Tag]:
    rows: list[Tag] = []
    for child in table.children:
        if not isinstance(child, Tag):
            continue
        name = _tag_name(child)
        if name == "tr":
            rows.append(child)
            continue
        if name in ROW_GROUP_TAGS:
            rows.extend(_direct_child_tags(child, {"tr"}))
    return rows


def _direct_row_cells(row: Tag) -> list[Tag]:
    return _direct_child_tags(row, {"th", "td"})


def _serialize_table_cell_text(cell: Tag) -> str:
    text = _collect_text(cell, exclude_tags={"table"})
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    lines = [TABLE_CELL_SPACE_PATTERN.sub(" ", line).strip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def _escape_tsv_cell(cell_text: str) -> str:
    return (
        cell_text.replace("\\", "\\\\")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\t", "\\t")
        .replace("\n", "\\n")
    )
