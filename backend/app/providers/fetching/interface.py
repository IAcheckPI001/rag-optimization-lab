from typing import Protocol

from app.schemas.extraction import FetchedContent


class UrlFetcher(Protocol):
    def fetch(self, url: str) -> FetchedContent:
        ...
