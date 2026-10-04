"""Shared enums for the agent system (spec §21-26). Kept in one module since
AgentRun, AgentStep, ToolCall, and Approval all reference these together.
"""

import enum


class AgentRunStatus(str, enum.Enum):
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"


class AgentStepState(str, enum.Enum):
    """Mirrors ADR-005's state machine — each persisted step records which
    state produced it, so a run's full transition history is inspectable
    after the fact, not just its final outcome.
    """

    PLANNING = "planning"
    TOOL_SELECTION = "tool_selection"
    TOOL_EXECUTION = "tool_execution"
    OBSERVATION = "observation"
    VERIFICATION = "verification"


class ToolRiskLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ToolCallStatus(str, enum.Enum):
    PENDING = "pending"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTED = "executed"
    FAILED = "failed"
    REJECTED = "rejected"


class ApprovalDecision(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
