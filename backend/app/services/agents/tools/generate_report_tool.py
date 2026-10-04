from pydantic import BaseModel, Field

from app.models.agent_enums import ToolRiskLevel
from app.services.agents.tools.base import WRITE_ROLES, Tool, ToolExecutionContext, ToolResult


class GenerateReportInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    query: str = Field(min_length=1, max_length=500)


class GenerateReportOutput(BaseModel):
    report: str
    source_count: int


class GenerateReportTool(Tool[GenerateReportInput]):
    name = "generate_report"
    description = (
        "Generates a short markdown report summarizing the organization's documents "
        "relevant to a topic. Internally searches the knowledge base, so a separate "
        "search_documents call isn't needed first."
    )
    risk_level = ToolRiskLevel.MEDIUM
    allowed_roles = WRITE_ROLES
    input_schema = GenerateReportInput
    output_schema = GenerateReportOutput

    async def _execute(
        self, arguments: GenerateReportInput, context: ToolExecutionContext
    ) -> ToolResult:
        results = await context.search_service.search(
            organization_id=context.organization_id, query=arguments.query, top_k=5
        )
        if not results:
            report = f"# {arguments.title}\n\nNo relevant documents were found for this topic."
            return ToolResult(success=True, output={"report": report, "source_count": 0})

        lines = [f"# {arguments.title}", "", f"_Generated from {len(results)} source(s)._", ""]
        for i, result in enumerate(results, start=1):
            lines.append(f"## Source {i}: {result.document_filename}")
            lines.append(result.chunk.content)
            lines.append("")
        report = "\n".join(lines)

        return ToolResult(success=True, output={"report": report, "source_count": len(results)})
