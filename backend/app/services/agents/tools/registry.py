"""The tool registry: every tool the agent can select from. Adding a new
tool means adding it here — nothing else in the agent system needs to know
about concrete tool classes.
"""

from typing import Any

from app.services.agents.tools.base import Tool
from app.services.agents.tools.calculate_tool import CalculateTool
from app.services.agents.tools.delete_document_tool import DeleteDocumentTool
from app.services.agents.tools.draft_email_tool import DraftEmailTool
from app.services.agents.tools.generate_report_tool import GenerateReportTool
from app.services.agents.tools.get_document_tool import GetDocumentTool
from app.services.agents.tools.safe_sql_tool import RunSafeSqlTool
from app.services.agents.tools.search_documents_tool import SearchDocumentsTool

_TOOLS: list[Tool[Any]] = [
    SearchDocumentsTool(),
    GetDocumentTool(),
    CalculateTool(),
    GenerateReportTool(),
    RunSafeSqlTool(),
    DeleteDocumentTool(),
    DraftEmailTool(),
]

TOOL_REGISTRY: dict[str, Tool[Any]] = {tool.name: tool for tool in _TOOLS}


def get_tool(name: str) -> Tool[Any] | None:
    return TOOL_REGISTRY.get(name)


def list_tools() -> list[Tool[Any]]:
    return list(_TOOLS)
