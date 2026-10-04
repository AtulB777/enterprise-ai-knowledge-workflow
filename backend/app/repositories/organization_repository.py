import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "organization"


class OrganizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, organization_id: uuid.UUID) -> Organization | None:
        result = await self._session.execute(
            select(Organization).where(Organization.id == organization_id)
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Organization | None:
        result = await self._session.execute(select(Organization).where(Organization.slug == slug))
        return result.scalar_one_or_none()

    async def _slug_exists(self, slug: str) -> bool:
        result = await self._session.execute(
            select(Organization.id).where(Organization.slug == slug)
        )
        return result.scalar_one_or_none() is not None

    async def create_with_unique_slug(self, *, name: str) -> Organization:
        base_slug = _slugify(name)
        slug = base_slug
        suffix = 1
        while await self._slug_exists(slug):
            suffix += 1
            slug = f"{base_slug}-{suffix}"

        organization = Organization(name=name, slug=slug)
        self._session.add(organization)
        await self._session.flush()
        return organization
