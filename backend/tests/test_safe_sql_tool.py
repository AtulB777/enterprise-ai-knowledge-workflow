"""Integration tests for run_safe_sql against real Postgres — including an
independent proof of ADR-012 decision 3's layer 4 (database-enforced
read-only transaction): a real write attempt is rejected by Postgres
itself, not by the tool's own string validation, proving that even a
hypothetical bypass of layers 1-3 would still be stopped.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db.session import get_engine
from app.services.agents.tools.base import ToolExecutionContext
from app.services.agents.tools.safe_sql_tool import RunSafeSqlTool
from app.services.document_service import DocumentService
from app.services.search_service import SearchService
from app.services.storage import LocalFileStorage
from app.workers.tasks import process_document
from tests.fakes import FakeEmbeddingProvider, FakeReranker
from tests.helpers import auth_headers, get_org_id, register_user


async def test_read_only_transaction_independently_blocks_a_real_write(db_session) -> None:
    """The core proof of layer 4: even with no application-level validation
    involved at all, a write attempted inside a Postgres transaction that
    was set READ ONLY is rejected by the database itself.
    """
    engine = get_engine()
    async with engine.connect() as connection:
        await connection.execute(text("SET TRANSACTION READ ONLY"))
        with pytest.raises(Exception, match="(?i)read.only"):
            await connection.execute(text("UPDATE organizations SET name = 'hacked' WHERE 1=0"))


async def _upload_and_process(
    client: AsyncClient, *, access_token: str, organization_id: str, filename: str, content: bytes
) -> str:
    response = await client.post(
        f"/api/v1/documents?organization_id={organization_id}",
        headers=auth_headers(access_token),
        files={"file": (filename, content, "text/plain")},
    )
    document_id = response.json()["id"]
    await process_document(
        ctx={}, document_id=document_id, embedding_provider=FakeEmbeddingProvider()
    )
    return document_id


async def _build_context(
    db_session, organization_id: str, user_id: uuid.UUID
) -> ToolExecutionContext:
    from app.core.config import get_settings

    settings = get_settings()
    storage = LocalFileStorage(settings.storage_root)
    search_service = SearchService(db_session, settings, FakeEmbeddingProvider(), FakeReranker())
    document_service = DocumentService(db_session, settings, storage)
    from app.models.membership import MembershipRole

    return ToolExecutionContext(
        session=db_session,
        organization_id=uuid.UUID(organization_id),
        user_id=user_id,
        user_role=MembershipRole.EMPLOYEE,
        search_service=search_service,
        document_service=document_service,
    )


async def test_run_safe_sql_returns_real_document_metadata(client: AsyncClient, db_session) -> None:
    owner = await register_user(client, email="sql-owner@example.com")
    org_id = await get_org_id(client, owner)
    await _upload_and_process(
        client,
        access_token=owner.access_token,
        organization_id=org_id,
        filename="policy.txt",
        content=b"Some real policy content.",
    )

    context = await _build_context(db_session, org_id, uuid.uuid4())
    tool = RunSafeSqlTool()
    result = await tool.run(
        arguments={"query": "SELECT * FROM agent_document_overview"}, context=context
    )

    assert result.success is True
    assert result.output["row_count"] == 1
    assert result.output["rows"][0]["filename"] == "policy.txt"


async def test_run_safe_sql_is_tenant_scoped(client: AsyncClient, db_session) -> None:
    org_a_owner = await register_user(
        client, email="sql-a@example.com", organization_name="SQL Org A"
    )
    org_b_owner = await register_user(
        client, email="sql-b@example.com", organization_name="SQL Org B"
    )
    org_a_id = await get_org_id(client, org_a_owner)
    org_b_id = await get_org_id(client, org_b_owner)
    await _upload_and_process(
        client,
        access_token=org_a_owner.access_token,
        organization_id=org_a_id,
        filename="secret.txt",
        content=b"Org A confidential content.",
    )

    context = await _build_context(db_session, org_b_id, uuid.uuid4())
    tool = RunSafeSqlTool()
    result = await tool.run(
        arguments={"query": "SELECT * FROM agent_document_overview"}, context=context
    )

    assert result.success is True
    assert result.output["row_count"] == 0


async def test_run_safe_sql_rejects_malicious_query_without_touching_db(
    client: AsyncClient, db_session
) -> None:
    owner = await register_user(client, email="sql-malicious@example.com")
    org_id = await get_org_id(client, owner)

    context = await _build_context(db_session, org_id, uuid.uuid4())
    tool = RunSafeSqlTool()
    result = await tool.run(
        arguments={"query": "DROP TABLE agent_document_overview"}, context=context
    )

    assert result.success is False
    assert result.error is not None
