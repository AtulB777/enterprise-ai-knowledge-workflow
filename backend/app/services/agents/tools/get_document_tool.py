import uuid

from pydantic import BaseModel, Field

from app.models.agent_enums import ToolRiskLevel
from app.services.agents.tools.base import ALL_ROLES, Tool, ToolExecutionContext, ToolResult
from app.services.exceptions import DocumentNotFoundError


class GetDocumentInput(BaseModel):
    document_id: str = Field(min_length=1, max_length=64)


class GetDocumentOutput(BaseModel):
    filename: str
    status: str
    extracted_text: str
    truncated: bool


class GetDocumentTool(Tool[GetDocumentInput]):
    name = "get_document"
    description = (
        "Retrieves metadata and extracted text for one specific document, given its ID "
        "(e.g. an ID returned by search_documents)."
    )
    risk_level = ToolRiskLevel.LOW
    allowed_roles = ALL_ROLES
    input_schema = GetDocumentInput
    output_schema = GetDocumentOutput

    async def _execute(
        self, arguments: GetDocumentInput, context: ToolExecutionContext
    ) -> ToolResult:
        try:
            document_id = uuid.UUID(arguments.document_id)
        except ValueError:
            return ToolResult(success=False, output={}, error="document_id must be a valid UUID.")

        try:
            document = await context.document_service.get_document(
                organization_id=context.organization_id, document_id=document_id
            )
        except DocumentNotFoundError:
            return ToolResult(success=False, output={}, error="Document not found.")

        # Truncated: this is agent context, not a full-document viewer — a
        # very long document would otherwise dominate the planner's context
        # budget for no proportional benefit.
        extracted_text = (document.extracted_text or "")[:2000]
        return ToolResult(
            success=True,
            output={
                "filename": document.original_filename,
                "status": document.status.value,
                "extracted_text": extracted_text,
                "truncated": len(document.extracted_text or "") > 2000,
            },
        )
