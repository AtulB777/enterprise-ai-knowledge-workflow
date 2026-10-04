import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentStatus


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        organization_id: uuid.UUID,
        collection_id: uuid.UUID | None,
        uploaded_by_user_id: uuid.UUID,
        original_filename: str,
        storage_path: str,
        content_type: str,
        size_bytes: int,
    ) -> Document:
        document = Document(
            organization_id=organization_id,
            collection_id=collection_id,
            uploaded_by_user_id=uploaded_by_user_id,
            original_filename=original_filename,
            storage_path=storage_path,
            content_type=content_type,
            size_bytes=size_bytes,
            status=DocumentStatus.PENDING,
        )
        self._session.add(document)
        await self._session.flush()
        return document

    async def get_by_id_for_org(
        self, *, document_id: uuid.UUID, organization_id: uuid.UUID
    ) -> Document | None:
        result = await self._session.execute(
            select(Document).where(
                Document.id == document_id, Document.organization_id == organization_id
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, document_id: uuid.UUID) -> Document | None:
        """Unscoped lookup — used only by the background worker, which
        operates on a document_id already known to be valid (enqueued by a
        tenant-scoped request) rather than on behalf of an HTTP caller.
        """
        result = await self._session.execute(select(Document).where(Document.id == document_id))
        return result.scalar_one_or_none()

    async def list_by_ids_for_org(
        self, *, organization_id: uuid.UUID, document_ids: list[uuid.UUID]
    ) -> list[Document]:
        """Batch lookup for enriching search results with document metadata
        (e.g. filename) without an N+1 query per result.
        """
        if not document_ids:
            return []
        result = await self._session.execute(
            select(Document).where(
                Document.organization_id == organization_id,
                Document.id.in_(document_ids),
            )
        )
        return list(result.scalars().all())

    async def list_for_org(
        self,
        *,
        organization_id: uuid.UUID,
        collection_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Document], int]:
        filters = [Document.organization_id == organization_id]
        if collection_id is not None:
            filters.append(Document.collection_id == collection_id)

        count_result = await self._session.execute(
            select(func.count()).select_from(Document).where(*filters)
        )
        total = count_result.scalar_one()

        result = await self._session.execute(
            select(Document)
            .where(*filters)
            .order_by(Document.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all()), total

    async def delete(self, document: Document) -> None:
        await self._session.delete(document)
        await self._session.flush()

    async def mark_processing(self, document: Document) -> None:
        document.status = DocumentStatus.PROCESSING
        await self._session.commit()

    async def mark_completed(self, document: Document, *, extracted_text: str) -> None:
        document.status = DocumentStatus.COMPLETED
        document.extracted_text = extracted_text
        document.extracted_char_count = len(extracted_text)
        document.processing_error = None
        document.processed_at = datetime.now(UTC)
        await self._session.commit()

    async def mark_failed(self, document: Document, *, error_message: str) -> None:
        document.status = DocumentStatus.FAILED
        document.processing_error = error_message
        document.processed_at = datetime.now(UTC)
        await self._session.commit()
