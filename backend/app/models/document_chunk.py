from __future__ import annotations

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import get_settings
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# The vector column's dimension is fixed at the DB schema level (pgvector
# requires a fixed size), so it's read once at import time from settings
# rather than being a runtime parameter — changing embedding models to one
# with a different output dimension requires a migration, which is the
# correct thing to force (see docs/adr — re-embedding on model change).
_EMBEDDING_DIMENSION = get_settings().embedding_dimension


class DocumentChunk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A chunk of a Document's extracted text, with its embedding.

    `organization_id` is denormalized from Document (not just reachable via
    a join) so tenant-scoped vector search can filter directly on this table
    without joining — see CLAUDE.md §3's tenant-scoping rule, which applies
    to this table exactly the same as any other tenant-owned data.

    `content_tsv` is a database-generated column (Postgres computes it from
    `content` on every write, not application code) — see ADR-001's decision
    to use Postgres full-text search rather than a separate search engine.
    Keeping it always in sync with `content` this way means there's no code
    path that can update `content` and forget to update the search index.
    """

    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_chunk_document_index"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)

    embedding: Mapped[list[float]] = mapped_column(Vector(_EMBEDDING_DIMENSION), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(255), nullable=False)

    content_tsv: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', content)", persisted=True),
        nullable=False,
    )
