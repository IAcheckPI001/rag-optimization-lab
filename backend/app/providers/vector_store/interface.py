from typing import Protocol

from app.schemas.retrieval import RetrievedContext


class VectorStore(Protocol):
    def upsert(self, *args: object, **kwargs: object) -> None:
        ...

    def search(self, *args: object, **kwargs: object) -> list[RetrievedContext]:
        ...
