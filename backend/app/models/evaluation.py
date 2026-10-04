from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class EvaluationRunStatus(str, enum.Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EvaluationRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One execution of `python -m evaluation.run` against a specific
    version of the golden dataset. `summary_metrics` holds the aggregate
    (mean-across-cases) values — per-case detail lives in EvaluationResult.
    """

    __tablename__ = "evaluation_runs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dataset_version: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[EvaluationRunStatus] = mapped_column(
        Enum(EvaluationRunStatus, name="evaluation_run_status"),
        nullable=False,
        default=EvaluationRunStatus.RUNNING,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary_metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    results: Mapped[list[EvaluationResult]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class EvaluationResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Per-golden-case metrics for one EvaluationRun. `metrics` is a flat
    JSONB dict (e.g. {"recall_at_5": 1.0, "mrr": 0.5, "citation_precision":
    1.0}) — kept flexible rather than one column per metric, since which
    metrics apply can grow (e.g. Phase 9 adds agent metrics) without a
    migration each time.
    """

    __tablename__ = "evaluation_results"

    evaluation_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    case_id: Mapped[str] = mapped_column(String(100), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped[EvaluationRun] = relationship(back_populates="results")
