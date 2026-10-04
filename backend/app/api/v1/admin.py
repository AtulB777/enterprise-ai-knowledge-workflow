"""Admin dashboard routes (ADR-018). Deliberately outside the per-organization
?organization_id= scoping every other router uses — these are platform-level
views (Decision 4), gated by require_platform_admin (Decision 1), not by
get_membership/require_roles the way tenant-scoped routes are.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_platform_admin
from app.db.session import get_db
from app.repositories.evaluation_repository import EvaluationRepository
from app.schemas.admin import (
    EvaluationResultResponse,
    EvaluationRunDetailResponse,
    EvaluationRunListResponse,
    EvaluationRunSummaryResponse,
    MetricsSummaryResponse,
)
from app.services.metrics_summary import build_metrics_summary

router = APIRouter(dependencies=[Depends(require_platform_admin)])


@router.get("/metrics-summary", response_model=MetricsSummaryResponse)
async def get_metrics_summary() -> MetricsSummaryResponse:
    summary = build_metrics_summary()
    return MetricsSummaryResponse(**summary.__dict__)


@router.get("/evaluations", response_model=EvaluationRunListResponse)
async def list_evaluation_runs(
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EvaluationRunListResponse:
    repo = EvaluationRepository(db)
    runs = await repo.list_all_runs(limit=limit, offset=offset)
    total = await repo.count_all_runs()
    return EvaluationRunListResponse(
        items=[
            EvaluationRunSummaryResponse(
                id=run.id,
                dataset_version=run.dataset_version,
                status=run.status.value,
                started_at=run.started_at,
                completed_at=run.completed_at,
                summary_metrics=run.summary_metrics,
                error_message=run.error_message,
            )
            for run in runs
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/evaluations/{run_id}", response_model=EvaluationRunDetailResponse)
async def get_evaluation_run(
    run_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EvaluationRunDetailResponse:
    run = await EvaluationRepository(db).get_run_by_id_any_org(run_id=run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    return EvaluationRunDetailResponse(
        id=run.id,
        dataset_version=run.dataset_version,
        status=run.status.value,
        started_at=run.started_at,
        completed_at=run.completed_at,
        summary_metrics=run.summary_metrics,
        error_message=run.error_message,
        results=[
            EvaluationResultResponse(
                id=r.id,
                case_id=r.case_id,
                query=r.query,
                metrics=r.metrics,
                latency_ms=r.latency_ms,
                error_message=r.error_message,
            )
            for r in run.results
        ],
    )
