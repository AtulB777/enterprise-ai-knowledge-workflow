import uuid

from pydantic import BaseModel, Field

from app.models.agent_enums import ToolRiskLevel
from app.services.agents.tools.base import DELETE_ROLES, Tool, ToolExecutionContext, ToolResult
from app.services.exceptions import DocumentNotFoundError


class DeleteDocumentInput(BaseModel):
    document_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=500)


class DeleteDocumentOutput(BaseModel):
    deleted_document_id: str
    reason: str


class DeleteDocumentTool(Tool[DeleteDocumentInput]):
    """A genuinely destructive action — same permanent effect as the
    DELETE /api/v1/documents/{id} endpoint from Phase 4. Classified HIGH_RISK
    specifically so there is at least one tool in the registry that proves
    human-approval gating actually blocks execution, not just describes it
    (spec §25) — see the AgentService state machine and ADR-012.
    """

    name = "delete_document"
    description = (
        "Permanently deletes a document from the organization's knowledge base. "
        "This cannot be undone. Requires human approval before it executes."
    )
    risk_level = ToolRiskLevel.HIGH
    allowed_roles = DELETE_ROLES
    input_schema = DeleteDocumentInput
    output_schema = DeleteDocumentOutput

    async def _execute(
        self, arguments: DeleteDocumentInput, context: ToolExecutionContext
    ) -> ToolResult:
        try:
            document_id = uuid.UUID(arguments.document_id)
        except ValueError:
            return ToolResult(success=False, output={}, error="document_id must be a valid UUID.")

        try:
            await context.document_service.delete_document(
                organization_id=context.organization_id, document_id=document_id
            )
        except DocumentNotFoundError:
            return ToolResult(success=False, output={}, error="Document not found.")

        return ToolResult(
            success=True,
            output={"deleted_document_id": str(document_id), "reason": arguments.reason},
        )
