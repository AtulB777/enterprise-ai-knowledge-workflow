from typing import Any

from pydantic import BaseModel


class ToolInfoResponse(BaseModel):
    name: str
    description: str
    risk_level: str
    allowed_roles: list[str]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
