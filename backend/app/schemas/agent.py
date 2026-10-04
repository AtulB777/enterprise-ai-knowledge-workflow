import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.agent_enums import (
    AgentRunStatus,
    AgentStepState,
    ApprovalDecision,
    ToolCallStatus,
    ToolRiskLevel,
)


class StartAgentRunRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)


class ApprovalDecisionRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=1000)


class AgentStepResponse(BaseModel):
    step_index: int
    state: AgentStepState
    reasoning: str
    created_at: datetime


class ApprovalResponse(BaseModel):
    id: uuid.UUID
    status: ApprovalDecision
    requested_at: datetime
    decided_at: datetime | None
    notes: str | None


class ToolCallResponse(BaseModel):
    id: uuid.UUID
    tool_name: str
    risk_level: ToolRiskLevel
    input_data: dict[str, Any]
    output_data: dict[str, Any] | None
    status: ToolCallStatus
    error_message: str | None
    approval: ApprovalResponse | None


class AgentRunResponse(BaseModel):
    id: uuid.UUID
    goal: str
    status: AgentRunStatus
    step_count: int
    max_steps: int
    final_answer: str | None
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None


class AgentRunDetailResponse(AgentRunResponse):
    steps: list[AgentStepResponse]
    tool_calls: list[ToolCallResponse]


class AgentRunListResponse(BaseModel):
    items: list[AgentRunResponse]
    total: int
    limit: int
    offset: int
