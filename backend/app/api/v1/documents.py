import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import CurrentMembership, require_roles
from app.core.config import Settings, get_settings
from app.core.file_validation import FileValidationError
from app.core.rate_limit import rate_limit_by_user
from app.db.session import get_db
from app.models.membership import Membership, MembershipRole
from app.schemas.document import DocumentDetailResponse, DocumentListResponse, DocumentResponse
from app.services.document_service import DocumentService
from app.services.exceptions import DocumentNotFoundError
from app.services.storage import get_file_storage

router = APIRouter()

# Uploading and deleting content are write actions gated to non-VIEWER roles;
# reading (list/get) is open to any confirmed member, VIEWER included, since
# "view-only" is exactly what that role means.
_WRITE_ROLES = (MembershipRole.ADMIN, MembershipRole.MANAGER, MembershipRole.EMPLOYEE)
_DELETE_ROLES = (MembershipRole.ADMIN, MembershipRole.MANAGER)

_settings_at_import = get_settings()
_upload_rate_limit = rate_limit_by_user(
    "upload", limit=_settings_at_import.rate_limit_upload_per_hour, window_seconds=3600
)


def _get_document_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DocumentService:
    return DocumentService(db, settings, get_file_storage())


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=DocumentResponse,
    dependencies=[Depends(_upload_rate_limit)],
)
async def upload_document(
    membership: Annotated[Membership, Depends(require_roles(*_WRITE_ROLES))],
    document_service: Annotated[DocumentService, Depends(_get_document_service)],
    file: Annotated[UploadFile, File()],
    collection_id: Annotated[uuid.UUID | None, Form()] = None,
) -> DocumentResponse:
    content = await file.read()
    try:
        document = await document_service.upload_document(
            organization_id=membership.organization_id,
            uploaded_by_user_id=membership.user_id,
            collection_id=collection_id,
            filename=file.filename or "unnamed",
            content=content,
        )
    except FileValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=exc.message
        ) from exc
    return DocumentResponse.model_validate(document)


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    membership: CurrentMembership,
    document_service: Annotated[DocumentService, Depends(_get_document_service)],
    collection_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentListResponse:
    items, total = await document_service.list_documents(
        organization_id=membership.organization_id,
        collection_id=collection_id,
        limit=limit,
        offset=offset,
    )
    return DocumentListResponse(
        items=[DocumentResponse.model_validate(d) for d in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    document_id: uuid.UUID,
    membership: CurrentMembership,
    document_service: Annotated[DocumentService, Depends(_get_document_service)],
) -> DocumentDetailResponse:
    try:
        document = await document_service.get_document(
            organization_id=membership.organization_id, document_id=document_id
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found."
        ) from exc
    return DocumentDetailResponse.model_validate(document)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    membership: Annotated[Membership, Depends(require_roles(*_DELETE_ROLES))],
    document_service: Annotated[DocumentService, Depends(_get_document_service)],
) -> None:
    try:
        await document_service.delete_document(
            organization_id=membership.organization_id, document_id=document_id
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found."
        ) from exc
