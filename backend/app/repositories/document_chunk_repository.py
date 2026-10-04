import uuid
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.document_chunk import DocumentChunk


class DocumentChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_all_for_document(
        self,
        *,
        organization_id: uuid.UUID,
        document_id: uuid.UUID,
        chunks: list[dict[str, Any]],
    ) -> list[DocumentChunk]:
        """Deletes any existing chunks for this document and inserts the new
        set. Used on (re-)ingestion — a document is always fully re-chunked,
        never incrementally patched, so there's no risk of stale leftover
        chunks from a previous embedding model/chunk-size configuration.
        """
        await self._session.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )
        rows = [
            DocumentChunk(
                organization_id=organization_id,
                document_id=document_id,
                chunk_index=c["chunk_index"],
                content=c["content"],
                char_count=c["char_count"],
                embedding=c["embedding"],
                embedding_model=c["embedding_model"],
            )
            for c in chunks
        ]
        self._session.add_all(rows)
        await self._session.flush()
        return rows

    async def count_for_document(
        self, *, organization_id: uuid.UUID, document_id: uuid.UUID
    ) -> int:
        result = await self._session.execute(
            select(DocumentChunk).where(
                DocumentChunk.organization_id == organization_id,
                DocumentChunk.document_id == document_id,
            )
        )
        return len(result.scalars().all())

    async def list_by_ids(
        self, *, organization_id: uuid.UUID, chunk_ids: list[uuid.UUID]
    ) -> list[DocumentChunk]:
        """Batch lookup for enriching citations with chunk content when
        displaying message history — avoids an N+1 query per citation.
        """
        if not chunk_ids:
            return []
        result = await self._session.execute(
            select(DocumentChunk).where(
                DocumentChunk.organization_id == organization_id,
                DocumentChunk.id.in_(chunk_ids),
            )
        )
        return list(result.scalars().all())

    async def find_similar(
        self,
        *,
        organization_id: uuid.UUID,
        query_embedding: list[float],
        limit: int,
        collection_id: uuid.UUID | None = None,
    ) -> list[tuple[DocumentChunk, float]]:
        """Real pgvector cosine-distance search, scoped to one tenant. Returns
        (chunk, similarity) pairs ordered most-similar first. `similarity` is
        1 - cosine_distance, i.e. 1.0 = identical direction, 0.0 = orthogonal
        — more intuitive for callers than raw distance.

        `collection_id` is optional metadata filtering (spec §15) — joins to
        Document since collection_id isn't denormalized onto chunks the way
        organization_id is (collection membership changes more often than
        tenant, so denormalizing it would need extra sync logic for little
        benefit at this scale).
        """
        distance = DocumentChunk.embedding.cosine_distance(query_embedding)
        stmt = select(DocumentChunk, distance.label("distance")).where(
            DocumentChunk.organization_id == organization_id
        )
        if collection_id is not None:
            stmt = stmt.join(Document, Document.id == DocumentChunk.document_id).where(
                Document.collection_id == collection_id
            )
        stmt = stmt.order_by(distance).limit(limit)

        result = await self._session.execute(stmt)
        return [(chunk, 1 - dist) for chunk, dist in result.all()]

    async def find_by_keyword(
        self,
        *,
        organization_id: uuid.UUID,
        query: str,
        limit: int,
        collection_id: uuid.UUID | None = None,
    ) -> list[tuple[DocumentChunk, float]]:
        """Real Postgres full-text search (ADR-001: no separate search engine
        at this scale). `plainto_tsquery` treats the query as plain text
        (handles punctuation/stray operators safely) rather than requiring
        the caller to write tsquery syntax. `ts_rank` scores are unbounded
        and not comparable to cosine similarity without normalization —
        callers combine this with `find_similar` via score fusion, not by
        comparing raw values directly.
        """
        tsquery = func.plainto_tsquery("english", query)
        rank = func.ts_rank(DocumentChunk.content_tsv, tsquery)
        stmt = select(DocumentChunk, rank.label("rank")).where(
            DocumentChunk.organization_id == organization_id,
            DocumentChunk.content_tsv.op("@@")(tsquery),
        )
        if collection_id is not None:
            stmt = stmt.join(Document, Document.id == DocumentChunk.document_id).where(
                Document.collection_id == collection_id
            )
        stmt = stmt.order_by(rank.desc()).limit(limit)

        result = await self._session.execute(stmt)
        return [(chunk, score) for chunk, score in result.all()]
