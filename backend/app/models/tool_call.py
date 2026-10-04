from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.agent_enums import ToolCallStatus, ToolRiskLevel

if TYPE_CHECKING:
    from app.models.agent_run import AgentRun
    from app.models.approval import Approval


class ToolCall(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One tool invocation the agent selected (spec §22/§23/§26). Every tool
    call is recorded regardless of outcome — including ones that were never
    executed because approval was rejected — so a run's full decision trail
    is inspectable.
    """

    __tablename__ = "tool_calls"

    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    risk_level: Mapped[ToolRiskLevel] = mapped_column(nullable=False)
    input_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    output_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[ToolCallStatus] = mapped_column(default=ToolCallStatus.PENDING, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    run: Mapped[AgentRun] = relationship(back_populates="tool_calls")
    approval: Mapped[Approval | None] = relationship(
        back_populates="tool_call", cascade="all, delete-orphan", uselist=False
    )
