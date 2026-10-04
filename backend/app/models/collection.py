from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.document import Document


class Collection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A folder-style grouping of documents within one organization. Flat for
    now (no nesting) — deliberately kept simple until a real need for nested
    folders shows up; see CLAUDE.md §60 on not overengineering ahead of need.
    """

    __tablename__ = "collections"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_collection_org_name"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    documents: Mapped[list[Document]] = relationship(back_populates="collection")
