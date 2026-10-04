import uuid

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    collection_id: uuid.UUID | None = None
    top_k: int | None = Field(default=None, ge=1, le=50)
    rerank: bool = True


class SearchResultResponse(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_filename: str
    chunk_index: int
    content: str
    semantic_score: float | None
    lexical_score: float | None
    hybrid_score: float
    rerank_score: float | None


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultResponse]
