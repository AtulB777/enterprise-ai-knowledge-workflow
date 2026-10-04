from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.message import Message


class Citation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single citation attached to an assistant Message. Only created for
    chunks the model actually referenced (by number) in its answer — never
    for every chunk retrieved. See ADR-010's citation validation step; this
    table is the persisted result of that validation, not raw retrieval
    output.
    """

    __tablename__ = "citations"
    __table_args__ = (
        UniqueConstraint("message_id", "citation_number", name="uq_citation_message_number"),
    )

    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_chunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    # The [n] number as it appeared in the model's answer text — preserves
    # the order/identity the model actually cited, independent of retrieval
    # ranking order.
    citation_number: Mapped[int] = mapped_column(Integer, nullable=False)
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False)

    message: Mapped[Message] = relationship(back_populates="citations")
