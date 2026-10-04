import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection
from app.repositories.collection_repository import CollectionRepository
from app.services.exceptions import DuplicateCollectionNameError


class CollectionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._collections = CollectionRepository(session)

    async def create_collection(
        self,
        *,
        organization_id: uuid.UUID,
        created_by_user_id: uuid.UUID,
        name: str,
        description: str | None,
    ) -> Collection:
        if await self._collections.name_exists(organization_id=organization_id, name=name):
            raise DuplicateCollectionNameError(name)

        collection = await self._collections.create(
            organization_id=organization_id,
            created_by_user_id=created_by_user_id,
            name=name,
            description=description,
        )
        await self._session.commit()
        return collection

    async def list_collections(self, *, organization_id: uuid.UUID) -> list[Collection]:
        return await self._collections.list_for_org(organization_id=organization_id)
