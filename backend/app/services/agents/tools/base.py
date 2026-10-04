"""Standardized tool interface (spec §22). Every tool subclasses `Tool` and
implements `_execute` against already-validated, typed input — the base
class's `run()` handles Pydantic validation of both input and output, plus
the exception safety net (a tool failure must never crash the agent loop,
same principle as the worker task's exception handling since Phase 4) so no
subclass has to duplicate any of that.
"""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar, Generic, TypeVar, cast

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_enums import ToolRiskLevel
from app.models.membership import MembershipRole
from app.services.document_service import DocumentService
from app.services.search_service import SearchService

InputSchemaT = TypeVar("InputSchemaT", bound=BaseModel)


@dataclass
class ToolExecutionContext:
    """Everything a tool might need, assembled once per agent run by
    AgentService and handed to every tool call — tools never construct
    their own DB sessions or service instances, so they can't accidentally
    bypass the tenant/permission scoping already established for the run.

    Deliberately does NOT carry the app's `Settings` object (see ADR-013,
    finding 2): none of the current tools need any setting, and the full
    object includes secrets (JWT signing key, every LLM provider's API key,
    DB/Redis URLs with embedded credentials). Tool output is echoed into the
    LLM conversation transcript and persisted, so exposing secrets here
    would be a real, not theoretical, leak surface. A future tool that
    genuinely needs a specific non-secret value should receive that exact
    value as its own field here, not the whole settings object back.
    """

    session: AsyncSession
    organization_id: uuid.UUID
    user_id: uuid.UUID
    user_role: MembershipRole
    search_service: SearchService
    document_service: DocumentService


@dataclass
class ToolResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None


# Shared role groups, matching the _WRITE_ROLES/_DELETE_ROLES convention
# already used in api/v1/documents.py — tools reference these rather than
# each repeating its own frozenset literal.
ALL_ROLES = frozenset(
    {MembershipRole.VIEWER, MembershipRole.EMPLOYEE, MembershipRole.MANAGER, MembershipRole.ADMIN}
)
WRITE_ROLES = frozenset({MembershipRole.EMPLOYEE, MembershipRole.MANAGER, MembershipRole.ADMIN})
DELETE_ROLES = frozenset({MembershipRole.MANAGER, MembershipRole.ADMIN})


class Tool(ABC, Generic[InputSchemaT]):
    """Generic over its own input schema (e.g. `class CalculateTool(Tool[CalculateInput])`)
    so each subclass's `_execute` can declare its specific Pydantic model as
    the argument type without violating the Liskov substitution principle —
    the alternative (every `_execute` typed against the bare `BaseModel`
    base class) would type-check but throw away the whole point of having a
    per-tool schema in the first place.
    """

    name: ClassVar[str]
    description: ClassVar[str]
    risk_level: ClassVar[ToolRiskLevel]
    allowed_roles: ClassVar[frozenset[MembershipRole]]
    # Not Generic-parametrized (ClassVar can't reference a class TypeVar) —
    # deliberately loosely typed here; run() bridges the gap with an
    # explicit cast after the dynamic Pydantic validation succeeds.
    input_schema: ClassVar[type[BaseModel]]
    # spec §22: every tool must declare an output schema, not just an input
    # one. Validated at runtime in run() below — this catches a tool whose
    # actual output has drifted from what it claims to produce, rather than
    # just documenting a shape and hoping implementations stay honest.
    output_schema: ClassVar[type[BaseModel]]

    async def run(self, *, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        try:
            validated = self.input_schema.model_validate(arguments)
        except ValidationError as exc:
            return ToolResult(success=False, output={}, error=f"Invalid arguments: {exc}")

        try:
            result = await self._execute(cast(InputSchemaT, validated), context)
        except Exception as exc:  # noqa: BLE001 - a tool failure must not crash the agent loop
            return ToolResult(success=False, output={}, error=f"Tool execution failed: {exc}")

        if result.success:
            try:
                self.output_schema.model_validate(result.output)
            except ValidationError as exc:
                # A tool bug, not a user-input problem — the tool claimed
                # success but produced output that doesn't match what it
                # declared it would. Surfacing this as a failure is safer
                # than letting mismatched data flow on to the LLM.
                return ToolResult(
                    success=False,
                    output={},
                    error=f"Tool '{self.name}' produced output that didn't match its "
                    f"declared output_schema: {exc}",
                )

        return result

    @abstractmethod
    async def _execute(
        self, arguments: InputSchemaT, context: ToolExecutionContext
    ) -> ToolResult: ...
