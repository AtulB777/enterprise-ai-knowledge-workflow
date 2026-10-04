from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.agent_enums import AgentStepState

if TYPE_CHECKING:
    from app.models.agent_run import AgentRun


class AgentStep(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One transition in an AgentRun's state machine (spec §21/§26).
    `reasoning` holds a human-readable summary for any step; `raw_action_json`
    additionally holds the exact JSON the planner returned for PLANNING steps
    — storing this verbatim (rather than reconstructing an equivalent from
    reasoning + a correlated ToolCall via timestamp inference) means transcript
    reconstruction for a resumed run is exact and unambiguous, not inferred.
    """

    __tablename__ = "agent_steps"

    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[AgentStepState] = mapped_column(nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    raw_action_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # Set on OBSERVATION steps — the ToolCall whose result this step reports on.
    tool_call_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tool_calls.id", ondelete="SET NULL"), nullable=True
    )

    run: Mapped[AgentRun] = relationship(back_populates="steps")
