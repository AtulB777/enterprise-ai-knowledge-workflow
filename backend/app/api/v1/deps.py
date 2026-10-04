"""Shared FastAPI dependencies: DB session, current-user auth, and the
tenant-membership / RBAC checks that protected, organization-scoped routes
are built on.

Every organization-scoped route depends on `get_membership`, which is the one
place that answers "does this user have any access to this organization at
all" — see CLAUDE.md §3 and ADR-006. Role-gated routes layer `require_roles`
on top of that, not instead of it.
"""

import uuid
from collections.abc import Callable
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.request_context import bind_organization_id, bind_user_id
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.membership import Membership, MembershipRole
from app.models.user import User
from app.repositories.membership_repository import MembershipRepository
from app.repositories.user_repository import UserRepository

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized

    try:
        payload = decode_access_token(
            credentials.credentials, secret=settings.jwt_secret, algorithm=settings.jwt_algorithm
        )
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise unauthorized from exc

    user = await UserRepository(db).get_by_id(user_id)
    if user is None or not user.is_active:
        raise unauthorized
    # Bound here, not in middleware (which runs before auth resolves) — see
    # ADR-014 decision 1. Every log line for the rest of this request now
    # carries user_id automatically.
    bind_user_id(str(user.id))
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_membership(
    organization_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Membership:
    """Resolves the current user's membership in the given organization.

    Returns 404 (not 403) when the user has no membership at all — per
    section 36, a user outside a tenant must not be able to distinguish
    "that organization doesn't exist" from "you're not in it."
    """
    membership = await MembershipRepository(db).get_for_user_and_org(
        user_id=current_user.id, organization_id=organization_id
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    bind_organization_id(str(organization_id))
    return membership


CurrentMembership = Annotated[Membership, Depends(get_membership)]


def require_roles(*allowed_roles: MembershipRole) -> Callable[[Membership], Membership]:
    """Role gate layered on top of get_membership. Existence of the org/
    membership is already established by the time this runs, so insufficient
    role is a 403 here (not a 404) — that distinction is safe to reveal to
    someone who is already a confirmed member of the organization.
    """

    def _check(membership: CurrentMembership) -> Membership:
        if membership.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return membership

    return _check


async def require_platform_admin(
    current_user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]
) -> User:
    """Gate for the admin dashboard (ADR-018 decision 1). This app has no
    separate platform-admin role — reuses "holds ADMIN in at least one
    organization" as the trust proxy, a deliberate scope decision, not an
    oversight. Unlike require_roles, this doesn't depend on get_membership
    at all: admin routes take no organization_id (they're platform-level,
    not tenant-level — see ADR-018 decision 4), so there's no single
    membership to check against in the first place.
    """
    memberships = await MembershipRepository(db).list_for_user(user_id=current_user.id)
    if not any(m.role == MembershipRole.ADMIN for m in memberships):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this.",
        )
    return current_user
