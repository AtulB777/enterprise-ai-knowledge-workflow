"""Hybrid search: semantic (pgvector) + keyword (Postgres full-text) fused
into one score, with optional cross-encoder reranking. See spec §15/§16,
ADR-002, ADR-008, ADR-009.
"""

import time
import uuid
from dataclasses import dataclass, replace

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.metrics import RETRIEVAL_LATENCY
from app.models.document_chunk import DocumentChunk
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.services.embeddings.provider import EmbeddingProvider
from app.services.reranking.reranker import Reranker


@dataclass(frozen=True)
class SearchResult:
    chunk: DocumentChunk
    document_id: uuid.UUID
    document_filename: str
    semantic_score: float | None
    lexical_score: float | None
    hybrid_score: float
    rerank_score: float | None


class SearchService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        embedding_provider: EmbeddingProvider,
        reranker: Reranker,
    ) -> None:
        self._session = session
        self._settings = settings
        self._embedding_provider = embedding_provider
        self._reranker = reranker
        self._chunks = DocumentChunkRepository(session)
        self._documents = DocumentRepository(session)

    async def search(
        self,
        *,
        organization_id: uuid.UUID,
        query: str,
        collection_id: uuid.UUID | None = None,
        top_k: int | None = None,
        rerank: bool = True,
    ) -> list[SearchResult]:
        top_k = top_k or self._settings.search_default_top_k
        pool_size = self._settings.search_candidate_pool_size
        start = time.monotonic()

        query_embedding = (await self._embedding_provider.embed([query]))[0]

        semantic_results = await self._chunks.find_similar(
            organization_id=organization_id,
            query_embedding=query_embedding,
            limit=pool_size,
            collection_id=collection_id,
        )
        lexical_results = await self._chunks.find_by_keyword(
            organization_id=organization_id,
            query=query,
            limit=pool_size,
            collection_id=collection_id,
        )

        fused = await self._fuse(organization_id, semantic_results, lexical_results)

        if rerank and fused:
            scores = await self._reranker.rerank(
                query=query, documents=[r.chunk.content for r in fused]
            )
            fused = [
                replace(result, rerank_score=score)
                for result, score in zip(fused, scores, strict=True)
            ]
            # rerank_score is guaranteed non-None here (just set above), but
            # the dataclass field type is float | None, so the fallback
            # keeps the sort key provably float-typed without a type: ignore.
            fused.sort(
                key=lambda r: r.rerank_score if r.rerank_score is not None else 0.0, reverse=True
            )
        else:
            fused.sort(key=lambda r: r.hybrid_score, reverse=True)

        RETRIEVAL_LATENCY.observe(time.monotonic() - start)
        return fused[:top_k]

    async def _fuse(
        self,
        organization_id: uuid.UUID,
        semantic_results: list[tuple[DocumentChunk, float]],
        lexical_results: list[tuple[DocumentChunk, float]],
    ) -> list[SearchResult]:
        alpha = self._settings.hybrid_search_alpha
        beta = self._settings.hybrid_search_beta

        semantic_scores = {chunk.id: score for chunk, score in semantic_results}
        lexical_scores = {chunk.id: score for chunk, score in lexical_results}
        chunks_by_id = {chunk.id: chunk for chunk, _ in semantic_results}
        chunks_by_id.update({chunk.id: chunk for chunk, _ in lexical_results})

        semantic_norm = _min_max_normalize(semantic_scores)
        lexical_norm = _min_max_normalize(lexical_scores)

        document_ids = {chunk.document_id for chunk in chunks_by_id.values()}
        documents = await self._documents.list_by_ids_for_org(
            organization_id=organization_id, document_ids=list(document_ids)
        )
        filenames_by_document_id = {doc.id: doc.original_filename for doc in documents}

        results = []
        for chunk_id, chunk in chunks_by_id.items():
            hybrid = alpha * semantic_norm.get(chunk_id, 0.0) + beta * lexical_norm.get(
                chunk_id, 0.0
            )
            results.append(
                SearchResult(
                    chunk=chunk,
                    document_id=chunk.document_id,
                    document_filename=filenames_by_document_id.get(chunk.document_id, "unknown"),
                    semantic_score=semantic_scores.get(chunk_id),
                    lexical_score=lexical_scores.get(chunk_id),
                    hybrid_score=hybrid,
                    rerank_score=None,
                )
            )
        return results


def _min_max_normalize(scores: dict[uuid.UUID, float]) -> dict[uuid.UUID, float]:
    if not scores:
        return {}
    values = list(scores.values())
    lo, hi = min(values), max(values)
    if hi == lo:
        # All equal (including the common single-result case) — treat as
        # fully relevant rather than dividing by zero.
        return dict.fromkeys(scores, 1.0)
    return {k: (v - lo) / (hi - lo) for k, v in scores.items()}
