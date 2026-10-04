from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import CurrentMembership
from app.core.config import Settings, get_settings
from app.core.rate_limit import rate_limit_by_user
from app.db.session import get_db
from app.schemas.search import SearchRequest, SearchResponse, SearchResultResponse
from app.services.embeddings.factory import get_embedding_provider
from app.services.embeddings.provider import EmbeddingProvider
from app.services.reranking.factory import get_reranker
from app.services.reranking.reranker import Reranker
from app.services.search_service import SearchService

router = APIRouter()

_settings_at_import = get_settings()
_search_rate_limit = rate_limit_by_user(
    "search", limit=_settings_at_import.rate_limit_search_per_minute, window_seconds=60
)


def _get_search_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    embedding_provider: Annotated[EmbeddingProvider, Depends(get_embedding_provider)],
    reranker: Annotated[Reranker, Depends(get_reranker)],
) -> SearchService:
    return SearchService(db, settings, embedding_provider, reranker)


@router.post("", response_model=SearchResponse, dependencies=[Depends(_search_rate_limit)])
async def search(
    body: SearchRequest,
    membership: CurrentMembership,
    search_service: Annotated[SearchService, Depends(_get_search_service)],
) -> SearchResponse:
    # Read-only — any confirmed member can search, VIEWER included, same
    # policy as document list/get (see api/v1/documents.py).
    results = await search_service.search(
        organization_id=membership.organization_id,
        query=body.query,
        collection_id=body.collection_id,
        top_k=body.top_k,
        rerank=body.rerank,
    )
    return SearchResponse(
        query=body.query,
        results=[
            SearchResultResponse(
                chunk_id=r.chunk.id,
                document_id=r.document_id,
                document_filename=r.document_filename,
                chunk_index=r.chunk.chunk_index,
                content=r.chunk.content,
                semantic_score=r.semantic_score,
                lexical_score=r.lexical_score,
                hybrid_score=r.hybrid_score,
                rerank_score=r.rerank_score,
            )
            for r in results
        ],
    )
