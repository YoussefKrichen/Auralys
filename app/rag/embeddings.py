from __future__ import annotations

import hashlib
from typing import Protocol


class EmbeddingProvider(Protocol):
    dimension: int

    def embed_query(self, text: str) -> list[float]:
        ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        ...


class FakeEmbeddingProvider:
    def __init__(self, dimension: int = 16) -> None:
        self.dimension = dimension

    def embed_query(self, text: str) -> list[float]:
        return self._embed_text(text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_text(text) for text in texts]

    def _embed_text(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        vector: list[float] = []
        while len(vector) < self.dimension:
            for value in digest:
                vector.append((value / 255.0) * 2.0 - 1.0)
                if len(vector) == self.dimension:
                    break
            digest = hashlib.sha256(digest).digest()
        return vector
