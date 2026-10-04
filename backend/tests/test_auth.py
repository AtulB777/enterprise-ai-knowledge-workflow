from httpx import AsyncClient
from sqlalchemy import select

from app.models.user import User
from tests.helpers import auth_headers, register_user


async def test_register_creates_user_org_and_admin_membership(
    client: AsyncClient, db_session
) -> None:
    result = await register_user(client, email="new@example.com")

    response = await client.get("/api/v1/users/me", headers=auth_headers(result.access_token))
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "new@example.com"
    assert len(body["memberships"]) == 1
    assert body["memberships"][0]["role"] == "admin"
    assert body["memberships"][0]["organization_name"] == "Acme Corp"


async def test_password_is_never_stored_in_plaintext(client: AsyncClient, db_session) -> None:
    await register_user(client, email="secure@example.com", password="correct-horse-1")

    result = await db_session.execute(select(User).where(User.email == "secure@example.com"))
    user = result.scalar_one()

    assert user.hashed_password != "correct-horse-1"
    assert user.hashed_password.startswith("$argon2id$")


async def test_register_duplicate_email_returns_409(client: AsyncClient) -> None:
    await register_user(client, email="dup@example.com")

    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "dup@example.com",
            "password": "another-pass-1",
            "full_name": "Someone Else",
            "organization_name": "Other Org",
        },
    )

    assert response.status_code == 409


async def test_register_rejects_weak_password(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "weak@example.com",
            "password": "short",
            "full_name": "Weak Password",
            "organization_name": "Org",
        },
    )

    assert response.status_code == 422


async def test_login_success_returns_tokens(client: AsyncClient) -> None:
    await register_user(client, email="login@example.com", password="correct-horse-1")

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "login@example.com", "password": "correct-horse-1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"


async def test_login_wrong_password_returns_401(client: AsyncClient) -> None:
    await register_user(client, email="wrongpw@example.com", password="correct-horse-1")

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "wrongpw@example.com", "password": "totally-wrong-1"},
    )

    assert response.status_code == 401


async def test_login_unknown_email_returns_401_not_404(client: AsyncClient) -> None:
    # Same status/shape as wrong password — must not let a client enumerate
    # registered emails by observing a different error for "no such user".
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "whatever-1"},
    )

    assert response.status_code == 401


async def test_protected_endpoint_rejects_missing_token(client: AsyncClient) -> None:
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401


async def test_protected_endpoint_rejects_garbage_token(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/users/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401


async def test_refresh_issues_new_tokens_and_rotates_old_one(client: AsyncClient) -> None:
    result = await register_user(client, email="refresh@example.com")

    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": result.refresh_token}
    )
    assert response.status_code == 200
    new_tokens = response.json()
    assert new_tokens["refresh_token"] != result.refresh_token
    assert new_tokens["access_token"] != result.access_token

    # The old refresh token was rotated out — reusing it must now fail.
    reuse_response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": result.refresh_token}
    )
    assert reuse_response.status_code == 401

    # But the newly issued refresh token works.
    second_response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": new_tokens["refresh_token"]}
    )
    assert second_response.status_code == 200


async def test_refresh_with_unknown_token_returns_401(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": "not-a-real-refresh-token"}
    )
    assert response.status_code == 401


async def test_logout_revokes_refresh_token(client: AsyncClient) -> None:
    result = await register_user(client, email="logout@example.com")

    logout_response = await client.post(
        "/api/v1/auth/logout", json={"refresh_token": result.refresh_token}
    )
    assert logout_response.status_code == 204

    refresh_response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": result.refresh_token}
    )
    assert refresh_response.status_code == 401


async def test_logout_with_unknown_token_is_not_an_error(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/logout", json={"refresh_token": "never-issued-token"}
    )
    assert response.status_code == 204
