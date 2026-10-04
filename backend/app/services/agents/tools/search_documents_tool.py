from pydantic import BaseModel, Field

from app.models.agent_enums import ToolRiskLevel
from app.services.agents.tools.base import ALL_ROLES, Tool, ToolExecutionContext, ToolResult


class SearchDocumentsInput(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)


class SearchResultItem(BaseModel):
    document_id: str
    document_filename: str
    content: str
    score: float


class SearchDocumentsOutput(BaseModel):
    results: list[SearchResultItem]


class SearchDocumentsTool(Tool[SearchDocumentsInput]):
    name = "search_documents"
    description = (
        "Searches the organization's documents using hybrid semantic + keyword search. "
        "Returns matching excerpts with their source document filenames and relevance scores."
    )
    risk_level = ToolRiskLevel.LOW
    allowed_roles = ALL_ROLES
    input_schema = SearchDocumentsInput
    output_schema = SearchDocumentsOutput

    async def _execute(
        self, arguments: SearchDocumentsInput, context: ToolExecutionContext
    ) -> ToolResult:
        results = await context.search_service.search(
            organization_id=context.organization_id,
            query=arguments.query,
            top_k=arguments.top_k,
        )
        return ToolResult(
            success=True,
            output={
                "results": [
                    {
                        "document_id": str(r.document_id),
                        "document_filename": r.document_filename,
                        "content": r.chunk.content,
                        "score": r.hybrid_score,
                    }
                    for r in results
                ]
            },
        )
