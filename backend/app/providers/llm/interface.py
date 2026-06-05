from typing import Protocol

from app.schemas.retrieval import RetrievedContext


class LLMProvider(Protocol):
    def generate(
        self,
        question: str,
        contexts: list[RetrievedContext],
    ) -> str:
        ...
