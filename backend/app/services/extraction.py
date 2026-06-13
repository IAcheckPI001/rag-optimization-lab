from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.providers.extraction.errors import (
    ExtractionError,
    ExtractionNoContentError,
    ExtractionParsingError,
)
from app.providers.extraction.interface import ContentExtractor
from app.providers.fetching.errors import UrlFetchError
from app.providers.fetching.interface import UrlFetcher
from app.schemas.extraction import ExtractionInput, ExtractionResult, FetchedContent
from app.schemas.source import ProcessingStage, SourceError, SourceType


RESERVED_EXTRA_METADATA_KEYS = frozenset({"fetch", "service"})


class ExtractionServiceInputError(ValueError):
    error_code = "extraction_service_input_error"
    retryable = False

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ExtractorNotRegisteredError(ExtractionServiceInputError):
    error_code = "extractor_not_registered"


class ExtractionServiceError(Exception):
    def __init__(self, source_error: SourceError) -> None:
        super().__init__(source_error.message)
        self.source_error = source_error


@dataclass(frozen=True)
class ExtractorRegistry:
    extractors: Mapping[SourceType, ContentExtractor]

    def get(self, source_type: SourceType) -> ContentExtractor:
        extractor = self.extractors.get(source_type)
        if extractor is None:
            raise ExtractorNotRegisteredError(
                f"No extractor is registered for source_type={source_type.value}."
            )
        return extractor


class ExtractionService:
    def __init__(
        self,
        *,
        registry: ExtractorRegistry,
        url_fetcher: UrlFetcher,
    ) -> None:
        self.registry = registry
        self.url_fetcher = url_fetcher

    def extract_bytes(
        self,
        *,
        source_id: str,
        document_id: str,
        source_type: SourceType,
        content_bytes: bytes,
        source_uri: str | None = None,
        original_filename: str | None = None,
        media_type: str | None = None,
        charset: str | None = None,
        extractor_config: dict[str, object] | None = None,
        extra_metadata: dict[str, object] | None = None,
    ) -> ExtractionResult:
        if source_type is SourceType.url:
            raise self._service_error(
                ExtractionServiceInputError(
                    "extract_bytes does not support source_type=url; use extract_url."
                )
            )

        try:
            safe_extra_metadata = _validated_caller_metadata(extra_metadata)
            extractor = self.registry.get(source_type)
            input_data = ExtractionInput(
                source_id=source_id,
                document_id=document_id,
                source_type=source_type,
                source_uri=source_uri,
                original_filename=original_filename,
                media_type=media_type,
                charset=charset,
                content_bytes=content_bytes,
                extractor_config=extractor_config or {},
                extra_metadata=safe_extra_metadata,
            )
            return extractor.extract(input_data)
        except ExtractionServiceInputError as exc:
            raise self._service_error(exc) from exc
        except ExtractionError as exc:
            raise self._service_error(exc) from exc

    def extract_url(
        self,
        *,
        source_id: str,
        document_id: str,
        url: str,
        extractor_config: dict[str, object] | None = None,
        extra_metadata: dict[str, object] | None = None,
    ) -> ExtractionResult:
        try:
            safe_extra_metadata = _validated_caller_metadata(extra_metadata)
            fetched = self.url_fetcher.fetch(url)
            extractor = self.registry.get(SourceType.url)
            input_data = ExtractionInput(
                source_id=source_id,
                document_id=document_id,
                source_type=SourceType.url,
                source_uri=fetched.final_url,
                media_type=fetched.media_type,
                charset=fetched.charset,
                content_bytes=fetched.content_bytes,
                extractor_config=extractor_config or {},
                extra_metadata={
                    **safe_extra_metadata,
                    "fetch": _safe_fetch_metadata(fetched),
                },
            )
            return extractor.extract(input_data)
        except ExtractionServiceInputError as exc:
            raise self._service_error(exc) from exc
        except UrlFetchError as exc:
            raise self._service_error(exc) from exc
        except ExtractionError as exc:
            raise self._service_error(exc) from exc

    def _service_error(
        self,
        error: ExtractionServiceInputError | UrlFetchError | ExtractionError,
    ) -> ExtractionServiceError:
        return ExtractionServiceError(map_to_source_error(error))


def map_to_source_error(
    error: ExtractionServiceInputError | UrlFetchError | ExtractionError,
) -> SourceError:
    if isinstance(error, UrlFetchError):
        return SourceError(
            error_code=error.error_code,
            message=error.message,
            failed_stage=ProcessingStage.downloading,
            retryable=error.retryable,
        )

    if isinstance(error, ExtractionParsingError):
        failed_stage = ProcessingStage.parsing
    elif isinstance(error, ExtractionNoContentError):
        failed_stage = ProcessingStage.extracting
    elif isinstance(error, ExtractionError):
        failed_stage = ProcessingStage.extracting
    else:
        failed_stage = ProcessingStage.extracting

    return SourceError(
        error_code=error.error_code,
        message=error.message,
        failed_stage=failed_stage,
        retryable=error.retryable,
    )


def _validated_caller_metadata(
    extra_metadata: dict[str, object] | None,
) -> dict[str, object]:
    metadata = dict(extra_metadata or {})
    reserved_keys = RESERVED_EXTRA_METADATA_KEYS.intersection(metadata)
    if reserved_keys:
        formatted = ", ".join(sorted(reserved_keys))
        raise ExtractionServiceInputError(
            f"extra_metadata contains reserved service keys: {formatted}."
        )
    return metadata


def _safe_fetch_metadata(fetched: FetchedContent) -> dict[str, object]:
    return {
        "original_url": fetched.original_url,
        "final_url": fetched.final_url,
        "status_code": fetched.status_code,
        "media_type": fetched.media_type,
        "charset": fetched.charset,
        "redirect_count": fetched.redirect_count,
        "extra_metadata": dict(fetched.extra_metadata),
    }
