from httpx import AsyncClient

from app.models.membership import Membership, MembershipRole
from tests.helpers import auth_headers, register_user


async def test_owner_can_read_their_own_organization(client: AsyncClient) -> None:
    owner = await register_user(client, email="owner1@example.com", organization_name="Org One")
    me = await client.get("/api/v1/users/me", headers=auth_headers(owner.access_token))
    org_id = me.json()["memberships"][0]["organization_id"]

    response = await client.get(
        f"/api/v1/organizations/{org_id}", headers=auth_headers(owner.access_token)
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Org One"


async def test_cross_tenant_read_returns_404_not_403(client: AsyncClient) -> None:
    """The central multi-tenancy guarantee from ADR-006: a user from Org A
    must not be able to access Org B's data, and the response must not even
    reveal whether Org B exists (404, not 403) — see spec section 36.
    """
    org_a_owner = await register_user(
        client, email="a-owner@example.com", organization_name="Org A"
    )
    org_b_owner = await register_user(
        client, email="b-owner@example.com", organization_name="Org B"
    )

    me_b = await client.get("/api/v1/users/me", headers=auth_headers(org_b_owner.access_token))
    org_b_id = me_b.json()["memberships"][0]["organization_id"]

    response = await client.get(
        f"/api/v1/organizations/{org_b_id}", headers=auth_headers(org_a_owner.access_token)
    )

    assert response.status_code == 404


async def test_cross_tenant_write_also_returns_404(client: AsyncClient) -> None:
    org_a_owner = await register_user(
        client, email="a-owner2@example.com", organization_name="Org A2"
    )
    org_b_owner = await register_user(
        client, email="b-owner2@example.com", organization_name="Org B2"
    )
    me_b = await client.get("/api/v1/users/me", headers=auth_headers(org_b_owner.access_token))
    org_b_id = me_b.json()["memberships"][0]["organization_id"]

    response = await client.patch(
        f"/api/v1/organizations/{org_b_id}",
        json={"name": "Hijacked Name"},
        headers=auth_headers(org_a_owner.access_token),
    )

    assert response.status_code == 404


async def test_admin_can_update_organization(client: AsyncClient) -> None:
    owner = await register_user(
        client, email="admin-update@example.com", organization_name="Updatable Org"
    )
    me = await client.get("/api/v1/users/me", headers=auth_headers(owner.access_token))
    org_id = me.json()["memberships"][0]["organization_id"]

    response = await client.patch(
        f"/api/v1/organizations/{org_id}",
        json={"name": "Renamed Org"},
        headers=auth_headers(owner.access_token),
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Renamed Org"


async def test_viewer_role_cannot_update_organization(client: AsyncClient, db_session) -> None:
    """RBAC gate: a VIEWER-role member is a confirmed member of the org (so
    this is a 403, not a 404 — see api/v1/deps.py's require_roles docstring)
    but must not be able to perform an ADMIN/MANAGER-only action.
    """
    owner = await register_user(
        client, email="viewer-org-owner@example.com", organization_name="Viewer Test Org"
    )
    me = await client.get("/api/v1/users/me", headers=auth_headers(owner.access_token))
    org_id = me.json()["memberships"][0]["organization_id"]

    # Register a second, separate account, then demote-by-construction: give
    # it a VIEWER membership on the first org directly via the DB, since
    # there is no (and should be no) public API for granting arbitrary roles
    # yet — that's an admin-invite flow for a later phase.
    viewer = await register_user(
        client, email="viewer@example.com", organization_name="Viewer's Own Org"
    )
    from sqlalchemy import select

    from app.models.user import User

    result = await db_session.execute(select(User).where(User.email == "viewer@example.com"))
    viewer_user = result.scalar_one()
    db_session.add(
        Membership(user_id=viewer_user.id, organization_id=org_id, role=MembershipRole.VIEWER)
    )
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/organizations/{org_id}",
        json={"name": "Should Not Work"},
        headers=auth_headers(viewer.access_token),
    )

    assert response.status_code == 403
