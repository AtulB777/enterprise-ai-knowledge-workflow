"""Reranker abstraction (see ADR-009). Mirrors the EmbeddingProvider pattern
from ADR-008: business logic depends only on this Protocol.
"""

from typing import Protocol


class Reranker(Protocol):
    async def rerank(self, *, query: str, documents: list[str]) -> list[float]:
        """Scores each document's relevance to `query`, returning one score
        per input document in the SAME order (not sorted) — callers pair
        scores back up with their own candidate list. Higher = more relevant;
        scores are only meaningful relative to each other within one call,
        not comparable across different queries or reranker instances.
        """
        ...
