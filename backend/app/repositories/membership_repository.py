import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.membership import Membership, MembershipRole


class MembershipRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, user_id: uuid.UUID, organization_id: uuid.UUID, role: MembershipRole
    ) -> Membership:
        membership = Membership(user_id=user_id, organization_id=organization_id, role=role)
        self._session.add(membership)
        await self._session.flush()
        return membership

    async def get_for_user_and_org(
        self, *, user_id: uuid.UUID, organization_id: uuid.UUID
    ) -> Membership | None:
        """The core tenant-isolation check: does this user have ANY membership
        in this organization? Every organization-scoped endpoint must go
        through this (or an equivalent org_id-filtered query) before touching
        that organization's data — see CLAUDE.md §3 and ADR-006.
        """
        result = await self._session.execute(
            select(Membership)
            .where(
                Membership.user_id == user_id,
                Membership.organization_id == organization_id,
            )
            .options(selectinload(Membership.organization))
        )
        return result.scalar_one_or_none()

    async def list_for_user(self, *, user_id: uuid.UUID) -> list[Membership]:
        result = await self._session.execute(
            select(Membership)
            .where(Membership.user_id == user_id)
            .options(selectinload(Membership.organization))
        )
        return list(result.scalars().all())
