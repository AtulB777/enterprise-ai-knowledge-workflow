import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class MetricsSummaryResponse(BaseModel):
    total_requests: int
    total_errors: int
    error_rate: float
    avg_request_latency_ms: float | None
    total_input_tokens: int
    total_output_tokens: int
    total_estimated_cost_usd: float
    avg_retrieval_latency_ms: float | None
    avg_llm_latency_ms: float | None
    total_agent_steps: int
    total_rate_limit_rejections: int


class EvaluationRunSummaryResponse(BaseModel):
    id: uuid.UUID
    dataset_version: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    summary_metrics: dict[str, Any]
    error_message: str | None


class EvaluationRunListResponse(BaseModel):
    items: list[EvaluationRunSummaryResponse]
    total: int
    limit: int
    offset: int


class EvaluationResultResponse(BaseModel):
    id: uuid.UUID
    case_id: str
    query: str
    metrics: dict[str, Any]
    latency_ms: float | None
    error_message: str | None


class EvaluationRunDetailResponse(EvaluationRunSummaryResponse):
    results: list[EvaluationResultResponse]
