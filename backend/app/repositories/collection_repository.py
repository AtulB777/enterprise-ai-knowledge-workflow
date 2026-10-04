import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection


class CollectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        organization_id: uuid.UUID,
        created_by_user_id: uuid.UUID,
        name: str,
        description: str | None,
    ) -> Collection:
        collection = Collection(
            organization_id=organization_id,
            created_by_user_id=created_by_user_id,
            name=name,
            description=description,
        )
        self._session.add(collection)
        await self._session.flush()
        return collection

    async def get_by_id_for_org(
        self, *, collection_id: uuid.UUID, organization_id: uuid.UUID
    ) -> Collection | None:
        result = await self._session.execute(
            select(Collection).where(
                Collection.id == collection_id, Collection.organization_id == organization_id
            )
        )
        return result.scalar_one_or_none()

    async def list_for_org(self, *, organization_id: uuid.UUID) -> list[Collection]:
        result = await self._session.execute(
            select(Collection)
            .where(Collection.organization_id == organization_id)
            .order_by(Collection.name)
        )
        return list(result.scalars().all())

    async def name_exists(self, *, organization_id: uuid.UUID, name: str) -> bool:
        result = await self._session.execute(
            select(Collection.id).where(
                Collection.organization_id == organization_id, Collection.name == name
            )
        )
        return result.scalar_one_or_none() is not None
