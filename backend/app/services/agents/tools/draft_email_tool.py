"""draft_email tool (spec §22 example, closing a gap noted in ADR-013).

Composes email text only — no SMTP integration exists anywhere in this
project, so this tool has no side effect at all; a human decides whether to
actually send what it produces. That's also why it's LOW risk: unlike a
real send_email tool (which spec §23 explicitly classifies HIGH_RISK), a
tool that only returns text for a human to review and send themselves
carries no real-world consequence on its own.
"""

from pydantic import BaseModel, Field

from app.models.agent_enums import ToolRiskLevel
from app.services.agents.tools.base import ALL_ROLES, Tool, ToolExecutionContext, ToolResult


class DraftEmailInput(BaseModel):
    recipient_description: str = Field(min_length=1, max_length=200)
    purpose: str = Field(min_length=1, max_length=1000)
    key_points: list[str] = Field(default_factory=list, max_length=10)


class DraftEmailOutput(BaseModel):
    subject: str
    body: str


class DraftEmailTool(Tool[DraftEmailInput]):
    name = "draft_email"
    description = (
        "Drafts an email (subject and body) for a given recipient and purpose. "
        "This ONLY composes text — it never sends anything, since no email-sending "
        "capability exists in this system. A human must review and send it themselves."
    )
    risk_level = ToolRiskLevel.LOW
    allowed_roles = ALL_ROLES
    input_schema = DraftEmailInput
    output_schema = DraftEmailOutput

    async def _execute(
        self, arguments: DraftEmailInput, context: ToolExecutionContext
    ) -> ToolResult:
        subject = arguments.purpose[:100]

        body_lines = [f"Dear {arguments.recipient_description},", "", arguments.purpose]
        if arguments.key_points:
            body_lines.append("")
            body_lines.extend(f"- {point}" for point in arguments.key_points)
        body_lines.extend(["", "Best regards,"])

        return ToolResult(success=True, output={"subject": subject, "body": "\n".join(body_lines)})
