from httpx import AsyncClient

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


async def test_search_returns_relevant_result_first(client: AsyncClient) -> None:
    owner = await register_user(client, email="search-api-owner@example.com")
    org_id = await get_org_id(client, owner)

    await _upload_and_process(
        client,
        access_token=owner.access_token,
        organization_id=org_id,
        filename="astronomy.txt",
        content=b"Telescopes observe distant galaxies and orbiting planets in deep space.",
    )
    await _upload_and_process(
        client,
        access_token=owner.access_token,
        organization_id=org_id,
        filename="cooking.txt",
        content=b"The recipe calls for fresh basil, garlic, and simmered tomato sauce.",
    )

    response = await client.post(
        f"/api/v1/search?organization_id={org_id}",
        headers=auth_headers(owner.access_token),
        json={"query": "galaxies and planets in space", "rerank": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "galaxies and planets in space"
    assert len(body["results"]) >= 1
    top = body["results"][0]
    assert "galaxies" in top["content"]
    assert top["rerank_score"] is not None
    assert top["hybrid_score"] is not None


async def test_search_without_rerank_still_returns_hybrid_scores(client: AsyncClient) -> None:
    owner = await register_user(client, email="search-norerank@example.com")
    org_id = await get_org_id(client, owner)

    await _upload_and_process(
        client,
        access_token=owner.access_token,
        organization_id=org_id,
        filename="doc.txt",
        content=b"Employee onboarding requires completing the compliance training module.",
    )

    response = await client.post(
        f"/api/v1/search?organization_id={org_id}",
        headers=auth_headers(owner.access_token),
        json={"query": "onboarding training", "rerank": False},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) == 1
    assert body["results"][0]["rerank_score"] is None
    assert body["results"][0]["hybrid_score"] > 0


async def test_search_respects_top_k(client: AsyncClient) -> None:
    owner = await register_user(client, email="search-topk@example.com")
    org_id = await get_org_id(client, owner)
    for i in range(5):
        await _upload_and_process(
            client,
            access_token=owner.access_token,
            organization_id=org_id,
            filename=f"policy{i}.txt",
            content=f"Company policy number {i} regarding remote work arrangements.".encode(),
        )

    response = await client.post(
        f"/api/v1/search?organization_id={org_id}",
        headers=auth_headers(owner.access_token),
        json={"query": "company policy remote work", "top_k": 2},
    )

    assert response.status_code == 200
    assert len(response.json()["results"]) == 2


async def test_search_filters_by_collection(client: AsyncClient) -> None:
    owner = await register_user(client, email="search-coll@example.com")
    org_id = await get_org_id(client, owner)

    collection_response = await client.post(
        f"/api/v1/collections?organization_id={org_id}",
        headers=auth_headers(owner.access_token),
        json={"name": "HR Docs"},
    )
    collection_id = collection_response.json()["id"]

    await client.post(
        f"/api/v1/documents?organization_id={org_id}",
        headers=auth_headers(owner.access_token),
        files={
            "file": ("in_collection.txt", b"Vacation policy details for HR Docs.", "text/plain")
        },
        data={"collection_id": collection_id},
    )
    in_collection_response = await client.get(
        f"/api/v1/documents?organization_id={org_id}", headers=auth_headers(owner.access_token)
    )
    in_collection_doc_id = in_collection_response.json()["items"][0]["id"]
    await process_document(
        ctx={}, document_id=in_collection_doc_id, embedding_provider=FakeEmbeddingProvider()
    )

    await _upload_and_process(
        client,
        access_token=owner.access_token,
        organization_id=org_id,
        filename="outside_collection.txt",
        content=b"Vacation policy details outside any collection.",
    )

    response = await client.post(
        f"/api/v1/search?organization_id={org_id}",
        headers=auth_headers(owner.access_token),
        json={"query": "vacation policy", "collection_id": collection_id},
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["document_filename"] == "in_collection.txt"


async def test_search_is_scoped_to_organization(client: AsyncClient) -> None:
    org_a_owner = await register_user(
        client, email="search-tenant-a@example.com", organization_name="Search Tenant A"
    )
    org_b_owner = await register_user(
        client, email="search-tenant-b@example.com", organization_name="Search Tenant B"
    )
    org_a_id = await get_org_id(client, org_a_owner)
    org_b_id = await get_org_id(client, org_b_owner)

    await _upload_and_process(
        client,
        access_token=org_a_owner.access_token,
        organization_id=org_a_id,
        filename="a.txt",
        content=b"Trade secret formula for the proprietary manufacturing process.",
    )

    response = await client.post(
        f"/api/v1/search?organization_id={org_b_id}",
        headers=auth_headers(org_b_owner.access_token),
        json={"query": "trade secret formula manufacturing"},
    )

    assert response.status_code == 200
    assert response.json()["results"] == []


async def test_search_requires_organization_membership(client: AsyncClient) -> None:
    org_a_owner = await register_user(
        client, email="search-notmember-a@example.com", organization_name="NotMember Org A"
    )
    org_b_owner = await register_user(
        client, email="search-notmember-b@example.com", organization_name="NotMember Org B"
    )
    org_a_id = await get_org_id(client, org_a_owner)

    response = await client.post(
        f"/api/v1/search?organization_id={org_a_id}",
        headers=auth_headers(org_b_owner.access_token),
        json={"query": "anything"},
    )

    assert response.status_code == 404


async def test_search_rejects_empty_query(client: AsyncClient) -> None:
    owner = await register_user(client, email="search-empty@example.com")
    org_id = await get_org_id(client, owner)

    response = await client.post(
        f"/api/v1/search?organization_id={org_id}",
        headers=auth_headers(owner.access_token),
        json={"query": ""},
    )

    assert response.status_code == 422
