import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import CurrentMembership, require_roles
from app.core.config import Settings, get_settings
from app.core.rate_limit import rate_limit_by_user
from app.db.session import get_db
from app.models.citation import Citation
from app.models.membership import Membership, MembershipRole
from app.models.message import Message
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.message_repository import MessageRepository
from app.schemas.chat import (
    AskRequest,
    CitationResponse,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationResponse,
    MessageResponse,
)
from app.services.conversation_service import ConversationService
from app.services.embeddings.factory import get_embedding_provider
from app.services.embeddings.provider import EmbeddingProvider
from app.services.exceptions import ConversationNotFoundError
from app.services.llm.factory import get_llm_provider
from app.services.llm.provider import LLMProvider
from app.services.rag_service import CitationResult, RagService
from app.services.reranking.factory import get_reranker
from app.services.reranking.reranker import Reranker
from app.services.search_service import SearchService

router = APIRouter()

_DELETE_ROLES = (MembershipRole.ADMIN, MembershipRole.MANAGER)
_settings_at_import = get_settings()
_chat_rate_limit = rate_limit_by_user(
    "chat", limit=_settings_at_import.rate_limit_chat_per_minute, window_seconds=60
)


def _to_citation_result(citation: Citation) -> CitationResult:
    """Normalizes a persisted Citation ORM row into the same CitationResult
    shape RagService.ask() produces fresh — so _build_citation_responses
    only ever handles one concrete type instead of two nominally different
    ones that happen to share field names (simpler and more mypy-friendly
    than a structural Protocol against SQLAlchemy's Mapped[] descriptors).
    """
    return CitationResult(
        citation_number=citation.citation_number,
        document_chunk_id=citation.document_chunk_id,
        document_id=citation.document_id,
        relevance_score=citation.relevance_score,
    )


def _get_conversation_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConversationService:
    return ConversationService(db)


def _get_rag_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    embedding_provider: Annotated[EmbeddingProvider, Depends(get_embedding_provider)],
    reranker: Annotated[Reranker, Depends(get_reranker)],
    llm_provider: Annotated[LLMProvider, Depends(get_llm_provider)],
) -> RagService:
    search_service = SearchService(db, settings, embedding_provider, reranker)
    return RagService(db, settings, search_service, llm_provider)


async def _build_citation_responses(
    db: AsyncSession,
    organization_id: uuid.UUID,
    citations: Sequence[CitationResult],
) -> list[CitationResponse]:
    """Enriches CitationResult objects with chunk content and document
    filename for the API response. Callers holding persisted Citation ORM
    rows (message history) normalize them via _to_citation_result first;
    RagService.ask()'s freshly-created CitationResult objects pass straight
    through.
    """
    chunk_ids = list({c.document_chunk_id for c in citations})
    document_ids = list({c.document_id for c in citations})

    chunks = await DocumentChunkRepository(db).list_by_ids(
        organization_id=organization_id, chunk_ids=chunk_ids
    )
    documents = await DocumentRepository(db).list_by_ids_for_org(
        organization_id=organization_id, document_ids=document_ids
    )
    content_by_chunk_id = {c.id: c.content for c in chunks}
    filename_by_document_id = {d.id: d.original_filename for d in documents}

    return [
        CitationResponse(
            citation_number=c.citation_number,
            document_id=c.document_id,
            document_filename=filename_by_document_id.get(c.document_id, "unknown"),
            chunk_content=content_by_chunk_id.get(c.document_chunk_id, ""),
            relevance_score=c.relevance_score,
        )
        for c in sorted(citations, key=lambda c: c.citation_number)
    ]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ConversationResponse)
async def create_conversation(
    membership: CurrentMembership,
    conversation_service: Annotated[ConversationService, Depends(_get_conversation_service)],
) -> ConversationResponse:
    conversation = await conversation_service.create_conversation(
        organization_id=membership.organization_id, created_by_user_id=membership.user_id
    )
    return ConversationResponse.model_validate(conversation)


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    membership: CurrentMembership,
    conversation_service: Annotated[ConversationService, Depends(_get_conversation_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ConversationListResponse:
    items, total = await conversation_service.list_conversations(
        organization_id=membership.organization_id, limit=limit, offset=offset
    )
    return ConversationListResponse(
        items=[ConversationResponse.model_validate(c) for c in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: uuid.UUID,
    membership: CurrentMembership,
    db: Annotated[AsyncSession, Depends(get_db)],
    conversation_service: Annotated[ConversationService, Depends(_get_conversation_service)],
) -> ConversationDetailResponse:
    try:
        conversation = await conversation_service.get_conversation(
            organization_id=membership.organization_id, conversation_id=conversation_id
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found."
        ) from exc

    messages = await MessageRepository(db).list_for_conversation(
        organization_id=membership.organization_id, conversation_id=conversation_id
    )
    message_responses = [
        MessageResponse(
            id=m.id,
            role=m.role,
            content=m.content,
            citations=await _build_citation_responses(
                db,
                membership.organization_id,
                [_to_citation_result(c) for c in m.citations],
            ),
            created_at=m.created_at,
        )
        for m in messages
    ]

    return ConversationDetailResponse(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=message_responses,
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: uuid.UUID,
    membership: Annotated[Membership, Depends(require_roles(*_DELETE_ROLES))],
    conversation_service: Annotated[ConversationService, Depends(_get_conversation_service)],
) -> None:
    try:
        await conversation_service.delete_conversation(
            organization_id=membership.organization_id, conversation_id=conversation_id
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found."
        ) from exc


@router.post(
    "/{conversation_id}/messages",
    status_code=status.HTTP_201_CREATED,
    response_model=MessageResponse,
    dependencies=[Depends(_chat_rate_limit)],
)
async def ask_question(
    conversation_id: uuid.UUID,
    body: AskRequest,
    membership: CurrentMembership,
    db: Annotated[AsyncSession, Depends(get_db)],
    conversation_service: Annotated[ConversationService, Depends(_get_conversation_service)],
    rag_service: Annotated[RagService, Depends(_get_rag_service)],
) -> MessageResponse:
    try:
        conversation = await conversation_service.get_conversation(
            organization_id=membership.organization_id, conversation_id=conversation_id
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found."
        ) from exc

    answer = await rag_service.ask(
        organization_id=membership.organization_id,
        conversation_id=conversation_id,
        question=body.question,
        collection_id=body.collection_id,
    )
    await conversation_service.maybe_set_title_from_first_message(
        conversation, first_question=body.question
    )

    message: Message = answer.message
    return MessageResponse(
        id=message.id,
        role=message.role,
        content=message.content,
        citations=await _build_citation_responses(db, membership.organization_id, answer.citations),
        created_at=message.created_at,
    )
