import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, organization_id: uuid.UUID, created_by_user_id: uuid.UUID
    ) -> Conversation:
        conversation = Conversation(
            organization_id=organization_id, created_by_user_id=created_by_user_id
        )
        self._session.add(conversation)
        await self._session.flush()
        return conversation

    async def get_by_id_for_org(
        self, *, conversation_id: uuid.UUID, organization_id: uuid.UUID
    ) -> Conversation | None:
        result = await self._session.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_org(
        self, *, organization_id: uuid.UUID, limit: int, offset: int
    ) -> tuple[list[Conversation], int]:
        count_result = await self._session.execute(
            select(func.count())
            .select_from(Conversation)
            .where(Conversation.organization_id == organization_id)
        )
        total = count_result.scalar_one()

        result = await self._session.execute(
            select(Conversation)
            .where(Conversation.organization_id == organization_id)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all()), total

    async def set_title(self, conversation: Conversation, *, title: str) -> None:
        conversation.title = title
        await self._session.flush()

    async def delete(self, conversation: Conversation) -> None:
        await self._session.delete(conversation)
        await self._session.flush()
