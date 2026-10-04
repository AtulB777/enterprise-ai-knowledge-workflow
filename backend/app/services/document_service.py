import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.file_validation import (
    FileValidationError,
    sanitize_display_filename,
    validate_upload,
)
from app.core.request_context import get_request_id
from app.models.document import Document
from app.repositories.collection_repository import CollectionRepository
from app.repositories.document_repository import DocumentRepository
from app.services.exceptions import DocumentNotFoundError
from app.services.storage import FileStorage
from app.workers.queue import get_arq_pool


class DocumentService:
    def __init__(self, session: AsyncSession, settings: Settings, storage: FileStorage) -> None:
        self._session = session
        self._settings = settings
        self._storage = storage
        self._documents = DocumentRepository(session)
        self._collections = CollectionRepository(session)

    async def upload_document(
        self,
        *,
        organization_id: uuid.UUID,
        uploaded_by_user_id: uuid.UUID,
        collection_id: uuid.UUID | None,
        filename: str,
        content: bytes,
    ) -> Document:
        # FileValidationError propagates to the route untranslated on purpose —
        # it already carries a client-safe message, unlike other ServiceErrors
        # which routes map to a generic message.
        max_size_bytes = self._settings.max_upload_size_mb * 1024 * 1024
        extension, sniffed_mime = validate_upload(
            filename=filename, content=content, max_size_bytes=max_size_bytes
        )

        if collection_id is not None:
            collection = await self._collections.get_by_id_for_org(
                collection_id=collection_id, organization_id=organization_id
            )
            if collection is None:
                raise FileValidationError("The specified collection does not exist.")

        storage_path = await self._storage.save(
            organization_id=organization_id, extension=extension, content=content
        )

        document = await self._documents.create(
            organization_id=organization_id,
            collection_id=collection_id,
            uploaded_by_user_id=uploaded_by_user_id,
            original_filename=sanitize_display_filename(filename),
            storage_path=storage_path,
            content_type=sniffed_mime,
            size_bytes=len(content),
        )
        await self._session.commit()

        pool = await get_arq_pool()
        # Propagates this request's correlation ID into the job — see
        # ADR-014 decision 3. The worker binds it into its own logging
        # context in process_document, so grepping logs for one request_id
        # surfaces both this upload request and the worker's later
        # processing of it, across the process boundary.
        await pool.enqueue_job("process_document", str(document.id), request_id=get_request_id())

        return document

    async def list_documents(
        self,
        *,
        organization_id: uuid.UUID,
        collection_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Document], int]:
        return await self._documents.list_for_org(
            organization_id=organization_id,
            collection_id=collection_id,
            limit=limit,
            offset=offset,
        )

    async def get_document(self, *, organization_id: uuid.UUID, document_id: uuid.UUID) -> Document:
        document = await self._documents.get_by_id_for_org(
            document_id=document_id, organization_id=organization_id
        )
        if document is None:
            raise DocumentNotFoundError(str(document_id))
        return document

    async def delete_document(self, *, organization_id: uuid.UUID, document_id: uuid.UUID) -> None:
        document = await self.get_document(organization_id=organization_id, document_id=document_id)
        await self._storage.delete(document.storage_path)
        await self._documents.delete(document)
        await self._session.commit()
