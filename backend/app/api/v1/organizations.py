from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import CurrentMembership, require_roles
from app.db.session import get_db
from app.models.membership import Membership, MembershipRole
from app.schemas.organization import OrganizationUpdateRequest
from app.schemas.user import OrganizationResponse

router = APIRouter()


@router.get("/{organization_id}", response_model=OrganizationResponse)
async def get_organization(
    membership: CurrentMembership,
) -> OrganizationResponse:
    # get_membership (behind CurrentMembership) already confirmed the caller
    # belongs to this organization and loaded it — this is the tenant-
    # isolation check, not an extra step on top of it.
    return OrganizationResponse.model_validate(membership.organization)


@router.patch("/{organization_id}", response_model=OrganizationResponse)
async def update_organization(
    body: OrganizationUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    membership: Annotated[
        Membership, Depends(require_roles(MembershipRole.ADMIN, MembershipRole.MANAGER))
    ],
) -> OrganizationResponse:
    organization = membership.organization
    organization.name = body.name
    await db.commit()
    await db.refresh(organization)
    return OrganizationResponse.model_validate(organization)
