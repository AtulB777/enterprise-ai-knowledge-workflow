"""Cross-encoder-backed reranker — the real, default implementation (ADR-009).

Lazy import for the same two reasons as
app/services/embeddings/sentence_transformers_provider.py: avoids paying for
a heavy dependency on every import, and lets this module's own logic
(pairing, batching, async offload) be unit-tested by mocking the import
boundary — see ADR-009's note on how this was verified.
"""

import asyncio
from typing import Any

from app.core.config import get_settings


class CrossEncoderReranker:
    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name or get_settings().reranker_model
        self._model: Any | None = None

    def _get_model(self) -> Any:
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self._model_name)
        return self._model

    async def rerank(self, *, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        return await asyncio.to_thread(self._score_sync, query, documents)

    def _score_sync(self, query: str, documents: list[str]) -> list[float]:
        model = self._get_model()
        pairs = [[query, doc] for doc in documents]
        scores = model.predict(pairs)
        return [float(s) for s in scores]
