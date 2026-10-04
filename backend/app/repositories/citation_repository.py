import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.citation import Citation


class CitationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_all(
        self, *, message_id: uuid.UUID, citations: list[dict[str, Any]]
    ) -> list[Citation]:
        rows = [
            Citation(
                message_id=message_id,
                document_chunk_id=c["document_chunk_id"],
                document_id=c["document_id"],
                citation_number=c["citation_number"],
                relevance_score=c["relevance_score"],
            )
            for c in citations
        ]
        self._session.add_all(rows)
        await self._session.flush()
        return rows
