from httpx import AsyncClient


async def test_security_headers_present_on_a_normal_response(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "permissions-policy" in response.headers


async def test_security_headers_present_on_an_error_response(client: AsyncClient) -> None:
    """The headers must land on error responses too, not just the happy
    path — this middleware is the outermost layer specifically so it
    applies regardless of what an inner layer (including an exception
    handler) does with the response.
    """
    response = await client.post(
        "/api/v1/auth/login", json={"email": "not-an-email", "password": ""}
    )

    assert response.status_code == 422
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
