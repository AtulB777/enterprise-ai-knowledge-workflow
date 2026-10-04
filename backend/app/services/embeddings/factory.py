from app.services.embeddings.provider import EmbeddingProvider
from app.services.embeddings.sentence_transformers_provider import (
    SentenceTransformersEmbeddingProvider,
)


def get_embedding_provider() -> EmbeddingProvider:
    # Only one real implementation exists yet (see ADR-008) — this factory is
    # still worth having now, same rationale as get_file_storage(): callers
    # depend on the Protocol, not a concrete class, so adding an
    # Ollama-served or API-based provider later is additive here only.
    return SentenceTransformersEmbeddingProvider()
