"""Regression test for a real bug found via live smoke testing in Phase 6:
Settings.debug defaulted to True, which makes Starlette's ServerErrorMiddleware
return raw Python tracebacks for unhandled exceptions — completely bypassing
app/main.py's custom JSON exception handler (Starlette checks self.debug
before checking for a registered Exception handler; see
ServerErrorMiddleware.__call__). Fixed by defaulting debug=False. This test
triggers a genuine unhandled exception (not caught anywhere in application
code) and confirms the response is the safe structured error shape, never a
traceback — the exact failure mode observed live.
"""

from httpx import ASGITransport, AsyncClient

from app.api.v1.search import _get_search_service
from app.main import app
from tests.helpers import auth_headers, get_org_id, register_user


class _ExplodingSearchService:
    async def search(self, **kwargs: object) -> None:
        raise RuntimeError("Simulated unexpected failure for regression testing.")


async def test_unhandled_exception_never_leaks_a_traceback_to_the_client(
    client: AsyncClient,
) -> None:
    owner = await register_user(client, email="debug-regression@example.com")
    org_id = await get_org_id(client, owner)

    app.dependency_overrides[_get_search_service] = lambda: _ExplodingSearchService()
    try:
        # raise_app_exceptions=False: observe the actual HTTP response a real
        # client receives, rather than httpx's test-convenience default of
        # re-raising the app's exception directly into the test.
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as raw_client:
            response = await raw_client.post(
                f"/api/v1/search?organization_id={org_id}",
                headers=auth_headers(owner.access_token),
                json={"query": "trigger the failure"},
            )
    finally:
        app.dependency_overrides.pop(_get_search_service, None)

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert "request_id" in body["error"]
    # The actual assertion that matters: no raw traceback content anywhere
    # in the response, regardless of status code or shape.
    assert "Traceback" not in response.text
    assert "RuntimeError" not in response.text
    assert "_ExplodingSearchService" not in response.text
    assert ".py" not in response.text
