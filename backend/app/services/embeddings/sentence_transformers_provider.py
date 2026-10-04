"""Sentence-transformers-backed embedding provider — the real, default
implementation (see ADR-008).

The `sentence_transformers` import is deliberately lazy (inside a method, not
the module top level) for two independent reasons:
  1. It's a heavy dependency (pulls in PyTorch) that shouldn't be paid for by
     every process that merely imports this module, e.g. Alembic, or code
     that only needs the Protocol type.
  2. It lets this module's own logic (batching, dimension validation, async
     offload) be unit-tested by mocking the import boundary, without the
     real package installed — see ADR-008's note on how this was verified.
"""

import asyncio
from typing import Any

from app.core.config import get_settings


class EmbeddingDimensionMismatchError(Exception):
    def __init__(self, *, expected: int, actual: int, model_name: str) -> None:
        self.message = (
            f"Model '{model_name}' produced {actual}-dimensional vectors, "
            f"expected {expected}. Check settings.embedding_dimension matches "
            f"the configured model, or a migration is needed to change it."
        )
        super().__init__(self.message)


class SentenceTransformersEmbeddingProvider:
    def __init__(
        self, model_name: str | None = None, expected_dimension: int | None = None
    ) -> None:
        settings = get_settings()
        self._model_name = model_name or settings.embedding_model
        self._expected_dimension = expected_dimension or settings.embedding_dimension
        self._model: Any | None = None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._expected_dimension

    def _get_model(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await asyncio.to_thread(self._encode_sync, texts)

    def _encode_sync(self, texts: list[str]) -> list[list[float]]:
        model = self._get_model()
        raw = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        vectors: list[list[float]] = raw.tolist()
        for vector in vectors:
            if len(vector) != self._expected_dimension:
                raise EmbeddingDimensionMismatchError(
                    expected=self._expected_dimension,
                    actual=len(vector),
                    model_name=self._model_name,
                )
        return vectors
