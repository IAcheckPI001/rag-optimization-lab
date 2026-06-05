from typing import Protocol

from app.schemas.document import RawDocumentUnit


class PDFExtractor(Protocol):
    def extract(self, file_path: str) -> list[RawDocumentUnit]:
        ...


class DocxExtractor(Protocol):
    def extract(self, file_path: str) -> list[RawDocumentUnit]:
        ...


class WebExtractor(Protocol):
    def extract(self, url: str) -> list[RawDocumentUnit]:
        ...
