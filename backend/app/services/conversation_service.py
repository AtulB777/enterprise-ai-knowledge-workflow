import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.services.exceptions import ConversationNotFoundError

__all__ = ["ConversationService", "ConversationNotFoundError"]


class ConversationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._conversations = ConversationRepository(session)
        self._messages = MessageRepository(session)

    async def create_conversation(
        self, *, organization_id: uuid.UUID, created_by_user_id: uuid.UUID
    ) -> Conversation:
        conversation = await self._conversations.create(
            organization_id=organization_id, created_by_user_id=created_by_user_id
        )
        await self._session.commit()
        return conversation

    async def get_conversation(
        self, *, organization_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> Conversation:
        conversation = await self._conversations.get_by_id_for_org(
            conversation_id=conversation_id, organization_id=organization_id
        )
        if conversation is None:
            raise ConversationNotFoundError(str(conversation_id))
        return conversation

    async def list_conversations(
        self, *, organization_id: uuid.UUID, limit: int, offset: int
    ) -> tuple[list[Conversation], int]:
        return await self._conversations.list_for_org(
            organization_id=organization_id, limit=limit, offset=offset
        )

    async def delete_conversation(
        self, *, organization_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> None:
        conversation = await self.get_conversation(
            organization_id=organization_id, conversation_id=conversation_id
        )
        await self._conversations.delete(conversation)
        await self._session.commit()

    async def maybe_set_title_from_first_message(
        self, conversation: Conversation, *, first_question: str
    ) -> None:
        if conversation.title is not None:
            return
        title = first_question[:100]
        await self._conversations.set_title(conversation, title=title)
        await self._session.commit()
