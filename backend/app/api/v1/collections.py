from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import CurrentMembership, require_roles
from app.db.session import get_db
from app.models.membership import Membership, MembershipRole
from app.schemas.document import CollectionCreateRequest, CollectionResponse
from app.services.collection_service import CollectionService
from app.services.exceptions import DuplicateCollectionNameError

router = APIRouter()

_WRITE_ROLES = (MembershipRole.ADMIN, MembershipRole.MANAGER, MembershipRole.EMPLOYEE)


def _get_collection_service(db: Annotated[AsyncSession, Depends(get_db)]) -> CollectionService:
    return CollectionService(db)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CollectionResponse)
async def create_collection(
    body: CollectionCreateRequest,
    membership: Annotated[Membership, Depends(require_roles(*_WRITE_ROLES))],
    collection_service: Annotated[CollectionService, Depends(_get_collection_service)],
) -> CollectionResponse:
    try:
        collection = await collection_service.create_collection(
            organization_id=membership.organization_id,
            created_by_user_id=membership.user_id,
            name=body.name,
            description=body.description,
        )
    except DuplicateCollectionNameError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A collection with this name already exists in this organization.",
        ) from exc
    return CollectionResponse.model_validate(collection)


@router.get("", response_model=list[CollectionResponse])
async def list_collections(
    membership: CurrentMembership,
    collection_service: Annotated[CollectionService, Depends(_get_collection_service)],
) -> list[CollectionResponse]:
    collections = await collection_service.list_collections(
        organization_id=membership.organization_id
    )
    return [CollectionResponse.model_validate(c) for c in collections]
