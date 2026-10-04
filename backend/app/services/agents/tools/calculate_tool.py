from pydantic import BaseModel, Field

from app.models.agent_enums import ToolRiskLevel
from app.services.agents.tools.base import ALL_ROLES, Tool, ToolExecutionContext, ToolResult
from app.services.agents.tools.safe_eval import UnsafeExpressionError, safe_eval


class CalculateInput(BaseModel):
    expression: str = Field(min_length=1, max_length=200)


class CalculateOutput(BaseModel):
    result: float


class CalculateTool(Tool[CalculateInput]):
    name = "calculate"
    description = (
        "Evaluates a basic arithmetic expression (+, -, *, /, %, **, parentheses). "
        "Use this for any numeric calculation rather than doing math yourself."
    )
    risk_level = ToolRiskLevel.LOW
    allowed_roles = ALL_ROLES
    input_schema = CalculateInput
    output_schema = CalculateOutput

    async def _execute(
        self, arguments: CalculateInput, context: ToolExecutionContext
    ) -> ToolResult:
        try:
            result = safe_eval(arguments.expression)
        except UnsafeExpressionError as exc:
            return ToolResult(success=False, output={}, error=exc.message)
        return ToolResult(success=True, output={"result": result})
