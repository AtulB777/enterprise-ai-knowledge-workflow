from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.agent_enums import ApprovalDecision

if TYPE_CHECKING:
    from app.models.tool_call import ToolCall
    from app.models.user import User


class Approval(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Human-in-the-loop approval for a HIGH_RISK ToolCall (spec §25). This
    row's existence and `status` ARE the enforcement mechanism — the agent
    loop checks this table before executing a high-risk tool, not a UI-only
    confirmation dialog that the backend would honor regardless.
    """

    __tablename__ = "approvals"

    tool_call_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tool_calls.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    status: Mapped[ApprovalDecision] = mapped_column(
        default=ApprovalDecision.PENDING, nullable=False
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    tool_call: Mapped[ToolCall] = relationship(back_populates="approval")
    decided_by: Mapped[User | None] = relationship()
