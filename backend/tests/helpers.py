from dataclasses import dataclass

from httpx import AsyncClient


@dataclass(frozen=True)
class RegisteredUser:
    email: str
    password: str
    access_token: str
    refresh_token: str


async def register_user(
    client: AsyncClient,
    *,
    email: str = "founder@example.com",
    password: str = "correct-horse-1",
    full_name: str = "Ada Founder",
    organization_name: str = "Acme Corp",
) -> RegisteredUser:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": full_name,
            "organization_name": organization_name,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return RegisteredUser(
        email=email,
        password=password,
        access_token=body["access_token"],
        refresh_token=body["refresh_token"],
    )


def auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def get_org_id(client: AsyncClient, user: RegisteredUser) -> str:
    response = await client.get("/api/v1/users/me", headers=auth_headers(user.access_token))
    return str(response.json()["memberships"][0]["organization_id"])
