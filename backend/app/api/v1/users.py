from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import CurrentUser
from app.db.session import get_db
from app.repositories.membership_repository import MembershipRepository
from app.schemas.user import MembershipResponse, UserResponse

router = APIRouter()


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    memberships = await MembershipRepository(db).list_for_user(user_id=current_user.id)
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
        memberships=[
            MembershipResponse(
                organization_id=m.organization_id,
                organization_name=m.organization.name,
                role=m.role,
            )
            for m in memberships
        ],
    )
