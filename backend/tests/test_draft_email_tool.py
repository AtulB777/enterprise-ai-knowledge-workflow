import uuid

from app.core.config import get_settings
from app.models.membership import MembershipRole
from app.services.agents.tools.base import ToolExecutionContext
from app.services.agents.tools.draft_email_tool import DraftEmailTool
from app.services.document_service import DocumentService
from app.services.search_service import SearchService
from app.services.storage import LocalFileStorage
from tests.fakes import FakeEmbeddingProvider, FakeReranker


def _make_context(db_session) -> ToolExecutionContext:
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


async def test_draft_email_produces_subject_and_body(db_session) -> None:
    tool = DraftEmailTool()
    context = _make_context(db_session)

    result = await tool.run(
        arguments={
            "recipient_description": "the finance team",
            "purpose": "Request approval for the Q3 budget increase.",
            "key_points": ["Increase covers new hires", "Effective next quarter"],
        },
        context=context,
    )

    assert result.success is True
    assert "finance team" in result.output["body"]
    assert "Request approval" in result.output["subject"]
    assert "Increase covers new hires" in result.output["body"]
    assert "Effective next quarter" in result.output["body"]


async def test_draft_email_works_without_key_points(db_session) -> None:
    tool = DraftEmailTool()
    context = _make_context(db_session)

    result = await tool.run(
        arguments={"recipient_description": "Alex", "purpose": "Follow up on our meeting."},
        context=context,
    )

    assert result.success is True
    assert "Alex" in result.output["body"]


async def test_draft_email_rejects_missing_purpose(db_session) -> None:
    tool = DraftEmailTool()
    context = _make_context(db_session)

    result = await tool.run(
        arguments={"recipient_description": "Alex"},
        context=context,
    )

    assert result.success is False
    assert "Invalid arguments" in result.error
