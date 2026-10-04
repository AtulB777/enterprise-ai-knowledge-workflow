import uuid

from httpx import AsyncClient

from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.workers.tasks import process_document
from tests.fakes import FakeEmbeddingProvider
from tests.helpers import auth_headers, get_org_id, register_user


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


async def test_keyword_search_matches_stemmed_forms(client: AsyncClient, db_session) -> None:
    """Proves real Postgres full-text search, not a substring match: the
    stored text says "foxes" and "jumping", the query says "fox" and "jump"
    — only true tsvector stemming makes this match.
    """
    owner = await register_user(client, email="kw-owner@example.com")
    org_id = await get_org_id(client, owner)

    await _upload_and_process(
        client,
        access_token=owner.access_token,
        organization_id=org_id,
        filename="animals.txt",
        content=b"The quick brown foxes are jumping over lazy dogs.",
    )

    chunk_repo = DocumentChunkRepository(db_session)
    results = await chunk_repo.find_by_keyword(
        organization_id=uuid.UUID(org_id), query="fox jump", limit=10
    )

    assert len(results) == 1
    assert "foxes" in results[0][0].content


async def test_keyword_search_ranks_more_relevant_chunk_higher(
    client: AsyncClient, db_session
) -> None:
    owner = await register_user(client, email="kw-rank@example.com")
    org_id = await get_org_id(client, owner)

    await _upload_and_process(
        client,
        access_token=owner.access_token,
        organization_id=org_id,
        filename="a.txt",
        content=b"Budget budget budget: the annual budget review covers budget allocation.",
    )
    await _upload_and_process(
        client,
        access_token=owner.access_token,
        organization_id=org_id,
        filename="b.txt",
        content=b"The company picnic is scheduled for next month in the park.",
    )

    chunk_repo = DocumentChunkRepository(db_session)
    results = await chunk_repo.find_by_keyword(
        organization_id=uuid.UUID(org_id), query="budget", limit=10
    )

    assert len(results) == 1
    assert "budget" in results[0][0].content.lower()


async def test_keyword_search_is_scoped_to_organization(client: AsyncClient, db_session) -> None:
    org_a_owner = await register_user(
        client, email="kw-a@example.com", organization_name="KW Org A"
    )
    org_b_owner = await register_user(
        client, email="kw-b@example.com", organization_name="KW Org B"
    )
    org_a_id = await get_org_id(client, org_a_owner)
    org_b_id = await get_org_id(client, org_b_owner)

    await _upload_and_process(
        client,
        access_token=org_a_owner.access_token,
        organization_id=org_a_id,
        filename="secret.txt",
        content=b"The confidential merger negotiation details are outlined here.",
    )

    chunk_repo = DocumentChunkRepository(db_session)
    results = await chunk_repo.find_by_keyword(
        organization_id=uuid.UUID(org_b_id), query="confidential merger negotiation", limit=10
    )

    assert results == []


async def test_keyword_search_no_match_returns_empty(client: AsyncClient, db_session) -> None:
    owner = await register_user(client, email="kw-nomatch@example.com")
    org_id = await get_org_id(client, owner)

    await _upload_and_process(
        client,
        access_token=owner.access_token,
        organization_id=org_id,
        filename="a.txt",
        content=b"Completely unrelated content about gardening tips.",
    )

    chunk_repo = DocumentChunkRepository(db_session)
    results = await chunk_repo.find_by_keyword(
        organization_id=uuid.UUID(org_id), query="quantum thermodynamics", limit=10
    )

    assert results == []
