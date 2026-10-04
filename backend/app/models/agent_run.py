from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.agent_enums import AgentRunStatus

if TYPE_CHECKING:
    from app.models.agent_step import AgentStep
    from app.models.tool_call import ToolCall


class AgentRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One execution of the agent (spec §21/§26). `max_steps`/
    `max_runtime_seconds`/`max_tool_calls` are stored per-run (not just read
    from current settings) so a completed run's limits are always
    reconstructable for audit, even if defaults change later.

    No raw conversation-history blob is stored — the planner reconstructs
    the transcript from this run's ordered AgentStep/ToolCall records on
    each resume (see ADR-012), so those tables are the single source of
    truth for a run's full history, not a duplicated cache of it.
    """

    __tablename__ = "agent_runs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[AgentRunStatus] = mapped_column(default=AgentRunStatus.RUNNING, nullable=False)
    step_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_steps: Mapped[int] = mapped_column(Integer, nullable=False)
    max_runtime_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    max_tool_calls: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    final_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    steps: Mapped[list[AgentStep]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="AgentStep.step_index"
    )
    tool_calls: Mapped[list[ToolCall]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="ToolCall.created_at"
    )
