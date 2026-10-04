from httpx import AsyncClient

from tests.helpers import auth_headers, get_org_id, register_user


async def test_create_collection(client: AsyncClient) -> None:
    owner = await register_user(client, email="coll-owner@example.com")
    org_id = await get_org_id(client, owner)

    response = await client.post(
        f"/api/v1/collections?organization_id={org_id}",
        headers=auth_headers(owner.access_token),
        json={"name": "HR Policies", "description": "Company HR documents"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "HR Policies"


async def test_duplicate_collection_name_in_same_org_returns_409(client: AsyncClient) -> None:
    owner = await register_user(client, email="coll-dup@example.com")
    org_id = await get_org_id(client, owner)
    await client.post(
        f"/api/v1/collections?organization_id={org_id}",
        headers=auth_headers(owner.access_token),
        json={"name": "Finance"},
    )

    response = await client.post(
        f"/api/v1/collections?organization_id={org_id}",
        headers=auth_headers(owner.access_token),
        json={"name": "Finance"},
    )

    assert response.status_code == 409


async def test_same_collection_name_allowed_in_different_orgs(client: AsyncClient) -> None:
    owner_a = await register_user(
        client, email="coll-a@example.com", organization_name="Coll Org A"
    )
    owner_b = await register_user(
        client, email="coll-b@example.com", organization_name="Coll Org B"
    )
    org_a_id = await get_org_id(client, owner_a)
    org_b_id = await get_org_id(client, owner_b)

    response_a = await client.post(
        f"/api/v1/collections?organization_id={org_a_id}",
        headers=auth_headers(owner_a.access_token),
        json={"name": "Legal"},
    )
    response_b = await client.post(
        f"/api/v1/collections?organization_id={org_b_id}",
        headers=auth_headers(owner_b.access_token),
        json={"name": "Legal"},
    )

    assert response_a.status_code == 201
    assert response_b.status_code == 201


async def test_list_collections_scoped_to_organization(client: AsyncClient) -> None:
    owner_a = await register_user(
        client, email="coll-list-a@example.com", organization_name="List Org A"
    )
    owner_b = await register_user(
        client, email="coll-list-b@example.com", organization_name="List Org B"
    )
    org_a_id = await get_org_id(client, owner_a)
    org_b_id = await get_org_id(client, owner_b)
    await client.post(
        f"/api/v1/collections?organization_id={org_a_id}",
        headers=auth_headers(owner_a.access_token),
        json={"name": "Org A Only"},
    )

    response = await client.get(
        f"/api/v1/collections?organization_id={org_b_id}",
        headers=auth_headers(owner_b.access_token),
    )

    assert response.status_code == 200
    names = [c["name"] for c in response.json()]
    assert "Org A Only" not in names
