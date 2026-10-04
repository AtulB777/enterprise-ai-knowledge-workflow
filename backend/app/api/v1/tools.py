"""Tool discovery/introspection API (ADR-013, finding 4). Read-only,
available to any authenticated user — this exposes tool *metadata*
(names, schemas, risk levels), the same for every organization, not any
tenant data, so it needs proof of authentication (CurrentUser) but not
organization membership (CurrentMembership, which would require an
organization_id this endpoint has no use for).
"""

from fastapi import APIRouter

from app.api.v1.deps import CurrentUser
from app.schemas.tool import ToolInfoResponse
from app.services.agents.tools.registry import list_tools

router = APIRouter()


@router.get("", response_model=list[ToolInfoResponse])
async def list_available_tools(current_user: CurrentUser) -> list[ToolInfoResponse]:
    del current_user  # only needed to require authentication
    return [
        ToolInfoResponse(
            name=tool.name,
            description=tool.description,
            risk_level=tool.risk_level.value,
            allowed_roles=sorted(role.value for role in tool.allowed_roles),
            input_schema=tool.input_schema.model_json_schema(),
            output_schema=tool.output_schema.model_json_schema(),
        )
        for tool in list_tools()
    ]
