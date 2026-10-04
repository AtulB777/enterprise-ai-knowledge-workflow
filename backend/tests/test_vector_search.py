import uuid

from httpx import AsyncClient

from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.workers.tasks import process_document
from tests.fakes import FakeEmbeddingProvider
from tests.helpers import auth_headers, get_org_id, register_user


async def _upload_and_process(
    client: AsyncClient,
    db_session,
    *,
    access_token: str,
    organization_id: str,
    filename: str,
    content: bytes,
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


async def test_similarity_search_returns_most_relevant_chunk_first(
    client: AsyncClient, db_session
) -> None:
    """The real proof this phase works: store chunks whose content clearly
    differs by topic, then confirm a real pgvector cosine-distance query
    (not a mock) ranks the chunk that shares the query's vocabulary above
    unrelated ones.
    """
    owner = await register_user(client, email="search-owner@example.com")
    org_id = await get_org_id(client, owner)

    await _upload_and_process(
        client,
        db_session,
        access_token=owner.access_token,
        organization_id=org_id,
        filename="astronomy.txt",
        content=b"Telescopes observe distant galaxies and orbiting planets in deep space.",
    )
    await _upload_and_process(
        client,
        db_session,
        access_token=owner.access_token,
        organization_id=org_id,
        filename="cooking.txt",
        content=b"The recipe calls for fresh basil, garlic, and simmered tomato sauce.",
    )
    await _upload_and_process(
        client,
        db_session,
        access_token=owner.access_token,
        organization_id=org_id,
        filename="finance.txt",
        content=b"Quarterly revenue grew as the company expanded into new markets.",
    )

    query_provider = FakeEmbeddingProvider()
    query_vector = (await query_provider.embed(["galaxies planets telescopes space"]))[0]

    chunk_repo = DocumentChunkRepository(db_session)
    results = await chunk_repo.find_similar(
        organization_id=uuid.UUID(org_id), query_embedding=query_vector, limit=3
    )

    assert len(results) == 3
    top_chunk, top_similarity = results[0]
    assert "galaxies" in top_chunk.content
    # The best match should score meaningfully higher than the rest.
    assert top_similarity > results[1][1]
    assert top_similarity > results[2][1]


async def test_similarity_search_is_scoped_to_organization(client: AsyncClient, db_session) -> None:
    org_a_owner = await register_user(
        client, email="search-a@example.com", organization_name="Search Org A"
    )
    org_b_owner = await register_user(
        client, email="search-b@example.com", organization_name="Search Org B"
    )
    org_a_id = await get_org_id(client, org_a_owner)
    org_b_id = await get_org_id(client, org_b_owner)

    await _upload_and_process(
        client,
        db_session,
        access_token=org_a_owner.access_token,
        organization_id=org_a_id,
        filename="secret.txt",
        content=b"Confidential org A trade secrets and proprietary formulas.",
    )

    query_provider = FakeEmbeddingProvider()
    query_vector = (await query_provider.embed(["Confidential org A trade secrets"]))[0]

    chunk_repo = DocumentChunkRepository(db_session)
    results_for_org_b = await chunk_repo.find_similar(
        organization_id=uuid.UUID(org_b_id), query_embedding=query_vector, limit=10
    )

    # Org B must see zero results even though the vector is a near-perfect
    # match for org A's chunk — tenant scope is enforced at the query level.
    assert results_for_org_b == []
