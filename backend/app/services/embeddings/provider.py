"""Embedding provider abstraction.

Mirrors the LLM provider abstraction (ADR-004): business logic (the chunking/
ingestion pipeline) depends only on this Protocol, never on a concrete
provider directly, so swapping the embedding backend later doesn't touch
calling code — see ADR-008.
"""

from typing import Protocol


class EmbeddingProvider(Protocol):
    @property
    def model_name(self) -> str:
        """Identifier stored on every embedded chunk (see DocumentChunk.embedding_model)
        so it's always known which model produced a given vector — required for safe
        re-embedding if the model ever changes (spec §14).
        """
        ...

    @property
    def dimension(self) -> int:
        """Output vector size. Must match the fixed pgvector column dimension
        (settings.embedding_dimension) — providers validate this themselves.
        """
        ...

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embeds a batch of texts, returning one vector per input text, in
        the same order. Batched rather than one-at-a-time so a real provider
        can use efficient batch inference.
        """
        ...
