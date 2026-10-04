"""Import every model here so Alembic's autogenerate (and Base.metadata.create_all
in tests) can discover them via a single import of this package.
"""

from app.models.agent_enums import (
    AgentRunStatus,
    AgentStepState,
    ApprovalDecision,
    ToolCallStatus,
    ToolRiskLevel,
)
from app.models.agent_run import AgentRun
from app.models.agent_step import AgentStep
from app.models.approval import Approval
from app.models.citation import Citation
from app.models.collection import Collection
from app.models.conversation import Conversation
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.models.evaluation import EvaluationResult, EvaluationRun, EvaluationRunStatus
from app.models.membership import Membership, MembershipRole
from app.models.message import Message, MessageRole
from app.models.organization import Organization
from app.models.refresh_token import RefreshToken
from app.models.tool_call import ToolCall
from app.models.user import User

__all__ = [
    "AgentRun",
    "AgentRunStatus",
    "AgentStep",
    "AgentStepState",
    "Approval",
    "ApprovalDecision",
    "Citation",
    "Collection",
    "Conversation",
    "Document",
    "DocumentChunk",
    "DocumentStatus",
    "EvaluationResult",
    "EvaluationRun",
    "EvaluationRunStatus",
    "Membership",
    "MembershipRole",
    "Message",
    "MessageRole",
    "Organization",
    "RefreshToken",
    "ToolCall",
    "ToolCallStatus",
    "ToolRiskLevel",
    "User",
]
