from httpx import AsyncClient


async def test_health_returns_ok_status_and_expected_shape(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["environment"] == "development"
    assert "app_name" in body


async def test_unknown_route_returns_structured_404(client: AsyncClient) -> None:
    response = await client.get("/api/v1/does-not-exist")

    assert response.status_code == 404


async def test_unknown_route_error_body_never_leaks_a_stack_trace(client: AsyncClient) -> None:
    response = await client.get("/api/v1/does-not-exist")

    body = response.text
    assert "Traceback" not in body
    assert 'File "' not in body
