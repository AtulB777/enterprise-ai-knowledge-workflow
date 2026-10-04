import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.evaluation import EvaluationResult, EvaluationRun, EvaluationRunStatus


class EvaluationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_run(
        self, *, organization_id: uuid.UUID, dataset_version: str
    ) -> EvaluationRun:
        run = EvaluationRun(
            organization_id=organization_id,
            dataset_version=dataset_version,
            status=EvaluationRunStatus.RUNNING,
            started_at=datetime.now(UTC),
            summary_metrics={},
        )
        self._session.add(run)
        await self._session.flush()
        return run

    async def add_result(
        self,
        *,
        run_id: uuid.UUID,
        case_id: str,
        query: str,
        metrics: dict[str, Any],
        latency_ms: float | None,
        error_message: str | None,
    ) -> EvaluationResult:
        result = EvaluationResult(
            evaluation_run_id=run_id,
            case_id=case_id,
            query=query,
            metrics=metrics,
            latency_ms=latency_ms,
            error_message=error_message,
        )
        self._session.add(result)
        await self._session.flush()
        return result

    async def complete_run(self, run: EvaluationRun, *, summary_metrics: dict[str, Any]) -> None:
        run.status = EvaluationRunStatus.COMPLETED
        run.completed_at = datetime.now(UTC)
        run.summary_metrics = summary_metrics
        await self._session.commit()

    async def fail_run(self, run: EvaluationRun, *, error_message: str) -> None:
        run.status = EvaluationRunStatus.FAILED
        run.completed_at = datetime.now(UTC)
        run.error_message = error_message
        await self._session.commit()

    async def get_previous_completed_run(
        self,
        *,
        organization_id: uuid.UUID,
        dataset_version: str,
        before_run_id: uuid.UUID,
    ) -> EvaluationRun | None:
        """The baseline for regression comparison (spec §28): the most
        recent COMPLETED run for the same dataset version, excluding the
        run currently in progress.
        """
        result = await self._session.execute(
            select(EvaluationRun)
            .where(
                EvaluationRun.organization_id == organization_id,
                EvaluationRun.dataset_version == dataset_version,
                EvaluationRun.status == EvaluationRunStatus.COMPLETED,
                EvaluationRun.id != before_run_id,
            )
            .order_by(EvaluationRun.started_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_runs_for_org(
        self, *, organization_id: uuid.UUID, limit: int, offset: int
    ) -> list[EvaluationRun]:
        result = await self._session.execute(
            select(EvaluationRun)
            .where(EvaluationRun.organization_id == organization_id)
            .order_by(EvaluationRun.started_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_run_by_id(
        self, *, organization_id: uuid.UUID, run_id: uuid.UUID
    ) -> EvaluationRun | None:
        result = await self._session.execute(
            select(EvaluationRun).where(
                EvaluationRun.id == run_id, EvaluationRun.organization_id == organization_id
            )
        )
        return result.scalar_one_or_none()

    # --- Platform-wide (admin dashboard, ADR-018 decision 2) ---
    #
    # Deliberately NOT filtered by organization_id, unlike every method
    # above: evaluation runs belong to the throwaway evaluation-dataset
    # organization Phase 8's runner creates, not any real customer org, so
    # an org-scoped query would always return empty for a real admin.

    async def list_all_runs(self, *, limit: int, offset: int) -> list[EvaluationRun]:
        result = await self._session.execute(
            select(EvaluationRun)
            .order_by(EvaluationRun.started_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_all_runs(self) -> int:
        result = await self._session.execute(select(func.count()).select_from(EvaluationRun))
        return result.scalar_one()

    async def get_run_by_id_any_org(self, *, run_id: uuid.UUID) -> EvaluationRun | None:
        result = await self._session.execute(
            select(EvaluationRun)
            .where(EvaluationRun.id == run_id)
            .options(selectinload(EvaluationRun.results))
        )
        return result.scalar_one_or_none()
