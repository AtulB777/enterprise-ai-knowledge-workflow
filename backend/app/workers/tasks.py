"""Background job(s) run by the arq worker process.

`process_document` is the full ingestion pipeline: read stored bytes ->
extract text -> chunk -> embed -> store chunks (with vectors) -> COMPLETED,
or FAILED with a real reason at whichever stage broke. COMPLETED now means
what the spec means by it — fully indexed and retrievable — not just "text
was extracted" (that was Phase 4's narrower meaning before chunking/embedding
existed).
"""

import logging
import uuid
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.request_context import bind_request_id, reset_context
from app.db.session import get_session_factory
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.services.chunking import chunk_text
from app.services.embeddings.factory import get_embedding_provider
from app.services.embeddings.provider import EmbeddingProvider
from app.services.extraction import ExtractionError, extract_text
from app.services.storage import get_file_storage

logger = logging.getLogger("app.workers")


async def process_document(
    ctx: dict[str, Any],
    document_id: str,
    *,
    embedding_provider: EmbeddingProvider | None = None,
    request_id: str | None = None,
) -> None:
    # embedding_provider is injectable for tests (see tests/fakes.py) — arq
    # itself always calls this with just (ctx, document_id, request_id=...),
    # which uses the real default provider. Same DI pattern as
    # DocumentService taking FileStorage in its constructor.
    #
    # request_id, if the enqueuing request supplied one (see
    # DocumentService.upload_document, ADR-014 decision 3), is bound here so
    # every log line this job emits correlates with that original HTTP
    # request — the practical substitute for full distributed tracing at
    # this system's scale. A job run without an originating request (e.g.
    # triggered directly, not via the API) simply has no request_id to bind.
    reset_context()
    if request_id is not None:
        bind_request_id(request_id)

    session_factory = get_session_factory()
    storage = get_file_storage()
    provider = embedding_provider or get_embedding_provider()
    settings = get_settings()

    async with session_factory() as session:
        repo = DocumentRepository(session)
        chunk_repo = DocumentChunkRepository(session)
        document = await repo.get_by_id(uuid.UUID(document_id))
        if document is None:
            logger.warning(
                "process_document: document not found", extra={"document_id": document_id}
            )
            return

        await repo.mark_processing(document)

        try:
            content = await storage.read(document.storage_path)
            extension = Path(document.storage_path).suffix
            text = await extract_text(extension=extension, content=content)

            chunks = chunk_text(
                text,
                chunk_size=settings.chunk_size_chars,
                chunk_overlap=settings.chunk_overlap_chars,
            )
            if not chunks:
                raise ExtractionError("No content available to index after chunking.")

            embeddings = await provider.embed([c.content for c in chunks])

            await chunk_repo.replace_all_for_document(
                organization_id=document.organization_id,
                document_id=document.id,
                chunks=[
                    {
                        "chunk_index": c.index,
                        "content": c.content,
                        "char_count": c.char_count,
                        "embedding": embedding,
                        "embedding_model": provider.model_name,
                    }
                    for c, embedding in zip(chunks, embeddings, strict=True)
                ],
            )
        except ExtractionError as exc:
            await session.rollback()
            logger.info(
                "process_document: extraction failed",
                extra={"document_id": document_id, "reason": exc.message},
            )
            await repo.mark_failed(document, error_message=exc.message)
            return
        except Exception as exc:  # noqa: BLE001 - a job failure must never crash the worker
            await session.rollback()
            logger.error(
                "process_document: unexpected error",
                extra={"document_id": document_id},
                exc_info=exc,
            )
            await repo.mark_failed(
                document, error_message="An unexpected error occurred during processing."
            )
            return

        await repo.mark_completed(document, extracted_text=text)
        logger.info(
            "process_document: completed",
            extra={"document_id": document_id, "chars": len(text), "chunks": len(chunks)},
        )
