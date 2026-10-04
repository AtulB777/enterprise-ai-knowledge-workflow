"""Tests for Tool.run()'s output_schema validation (ADR-013, finding 1).
Uses a deliberately misbehaving test-only tool to prove the validation
actually catches a mismatch — a test that only exercises the correct path
wouldn't prove the check does anything.
"""

from pydantic import BaseModel

from app.models.agent_enums import ToolRiskLevel
from app.services.agents.tools.base import ALL_ROLES, Tool, ToolExecutionContext, ToolResult


class _EchoInput(BaseModel):
    value: str


class _ExpectedOutput(BaseModel):
    count: int


class _WellBehavedTool(Tool[_EchoInput]):
    name = "test_well_behaved"
    description = "test tool that returns output matching its schema"
    risk_level = ToolRiskLevel.LOW
    allowed_roles = ALL_ROLES
    input_schema = _EchoInput
    output_schema = _ExpectedOutput

    async def _execute(self, arguments: _EchoInput, context: ToolExecutionContext) -> ToolResult:
        return ToolResult(success=True, output={"count": len(arguments.value)})


class _MisbehavedTool(Tool[_EchoInput]):
    """Deliberately returns output that does NOT match output_schema —
    simulates a real tool implementation bug.
    """

    name = "test_misbehaved"
    description = "test tool that returns output NOT matching its schema"
    risk_level = ToolRiskLevel.LOW
    allowed_roles = ALL_ROLES
    input_schema = _EchoInput
    output_schema = _ExpectedOutput

    async def _execute(self, arguments: _EchoInput, context: ToolExecutionContext) -> ToolResult:
        # Wrong key entirely, and wrong type — output_schema expects {"count": int}.
        return ToolResult(success=True, output={"wrong_key": "not a number"})


def _make_context(db_session) -> ToolExecutionContext:
    import uuid

    from app.core.config import get_settings
    from app.models.membership import MembershipRole
    from app.services.document_service import DocumentService
    from app.services.search_service import SearchService
    from app.services.storage import LocalFileStorage
    from tests.fakes import FakeEmbeddingProvider, FakeReranker

    settings = get_settings()
    storage = LocalFileStorage(settings.storage_root)
    search_service = SearchService(db_session, settings, FakeEmbeddingProvider(), FakeReranker())
    document_service = DocumentService(db_session, settings, storage)

    return ToolExecutionContext(
        session=db_session,
        organization_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        user_role=MembershipRole.ADMIN,
        search_service=search_service,
        document_service=document_service,
    )


async def test_output_matching_schema_passes_through(db_session) -> None:
    tool = _WellBehavedTool()
    context = _make_context(db_session)

    result = await tool.run(arguments={"value": "hello"}, context=context)

    assert result.success is True
    assert result.output == {"count": 5}


async def test_output_not_matching_schema_is_converted_to_failure(db_session) -> None:
    """The actual proof: a tool that claims success but returns the wrong
    shape must not have that malformed data silently pass through to the
    agent loop / LLM transcript.
    """
    tool = _MisbehavedTool()
    context = _make_context(db_session)

    result = await tool.run(arguments={"value": "hello"}, context=context)

    assert result.success is False
    assert "output_schema" in result.error
    assert result.output == {}
