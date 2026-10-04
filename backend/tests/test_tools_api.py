from httpx import AsyncClient

from tests.helpers import auth_headers, register_user


async def test_list_tools_returns_all_registered_tools(client: AsyncClient) -> None:
    owner = await register_user(client, email="tools-owner@example.com")

    response = await client.get("/api/v1/tools", headers=auth_headers(owner.access_token))

    assert response.status_code == 200
    body = response.json()
    names = {t["name"] for t in body}
    assert names == {
        "search_documents",
        "get_document",
        "calculate",
        "generate_report",
        "run_safe_sql",
        "delete_document",
        "draft_email",
    }


async def test_tool_info_includes_risk_level_and_schemas(client: AsyncClient) -> None:
    owner = await register_user(client, email="tools-schema@example.com")

    response = await client.get("/api/v1/tools", headers=auth_headers(owner.access_token))

    body = response.json()
    calculate_tool = next(t for t in body if t["name"] == "calculate")
    assert calculate_tool["risk_level"] == "low"
    assert "viewer" in calculate_tool["allowed_roles"]
    assert "properties" in calculate_tool["input_schema"]
    assert "expression" in calculate_tool["input_schema"]["properties"]
    assert "properties" in calculate_tool["output_schema"]
    assert "result" in calculate_tool["output_schema"]["properties"]

    delete_tool = next(t for t in body if t["name"] == "delete_document")
    assert delete_tool["risk_level"] == "high"
    assert "viewer" not in delete_tool["allowed_roles"]
    assert "manager" in delete_tool["allowed_roles"]


async def test_list_tools_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/tools")
    assert response.status_code == 401
