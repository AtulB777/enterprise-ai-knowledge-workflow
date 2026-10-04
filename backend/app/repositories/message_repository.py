import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.message import Message, MessageRole


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        organization_id: uuid.UUID,
        conversation_id: uuid.UUID,
        role: MessageRole,
        content: str,
    ) -> Message:
        message = Message(
            organization_id=organization_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
        )
        self._session.add(message)
        await self._session.flush()
        return message

    async def list_for_conversation(
        self, *, organization_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> list[Message]:
        result = await self._session.execute(
            select(Message)
            .where(
                Message.organization_id == organization_id,
                Message.conversation_id == conversation_id,
            )
            .options(selectinload(Message.citations))
            .order_by(Message.created_at)
        )
        return list(result.scalars().all())
