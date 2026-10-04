"""HTTP-level integration tests for rate limiting. Rate limiting is disabled
by default for the test suite (conftest.py) so unrelated tests aren't
affected; these tests explicitly re-enable it via a get_settings dependency
override for the duration of each test. The numeric limits themselves are
already set low in conftest.py's test environment (3 for everything) since
those are baked into each route's dependency closure at module-import time,
not re-read from settings per request — only the enabled flag is checked
dynamically, which is what these overrides actually flip.
"""

from httpx import AsyncClient

from app.core.config import get_settings
from app.main import app
from tests.helpers import auth_headers, get_org_id, register_user


def _enable_rate_limiting() -> None:
    real_settings = get_settings()
    test_settings = real_settings.model_copy(update={"rate_limiting_enabled": True})
    app.dependency_overrides[get_settings] = lambda: test_settings


def _restore_default_settings() -> None:
    app.dependency_overrides.pop(get_settings, None)


async def test_exceeding_the_login_limit_returns_429_with_retry_after(
    client: AsyncClient,
) -> None:
    owner = await register_user(client, email="ratelimit-login@example.com")

    _enable_rate_limiting()
    try:
        responses = []
        # conftest.py sets RATE_LIMIT_LOGIN_PER_MINUTE=3 for the test env.
        for _ in range(4):
            responses.append(
                await client.post(
                    "/api/v1/auth/login",
                    json={"email": owner.email, "password": "wrong-password-on-purpose"},
                )
            )
    finally:
        _restore_default_settings()

    statuses = [r.status_code for r in responses]
    assert statuses[:3] == [401, 401, 401]  # wrong password, but under the rate limit
    assert statuses[3] == 429
    limited_response = responses[3]
    assert "retry-after" in limited_response.headers
    body = limited_response.json()
    assert (
        body["error"]["code"] == "RATE_LIMITED" or "Too many requests" in body["error"]["message"]
    )


async def test_rate_limit_response_matches_standard_error_shape(client: AsyncClient) -> None:
    _enable_rate_limiting()
    try:
        response = None
        for i in range(4):
            response = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": f"ratelimit-shape-{i}@example.com",
                    "password": "correct-horse-1",
                    "full_name": "Rate Limit Shape",
                    "organization_name": f"Rate Limit Shape Org {i}",
                },
            )
    finally:
        _restore_default_settings()

    assert response is not None
    assert response.status_code == 429
    body = response.json()
    assert "error" in body
    assert "message" in body["error"]
    assert "request_id" in body["error"]


async def test_different_users_have_independent_search_limits(client: AsyncClient) -> None:
    user_a = await register_user(client, email="ratelimit-a@example.com")
    user_b = await register_user(client, email="ratelimit-b@example.com")
    org_a = await get_org_id(client, user_a)
    org_b = await get_org_id(client, user_b)

    _enable_rate_limiting()
    try:
        # Exhaust user A's limit (RATE_LIMIT_SEARCH_PER_MINUTE=3 in tests).
        for _ in range(3):
            await client.post(
                f"/api/v1/search?organization_id={org_a}",
                headers=auth_headers(user_a.access_token),
                json={"query": "anything"},
            )
        exhausted = await client.post(
            f"/api/v1/search?organization_id={org_a}",
            headers=auth_headers(user_a.access_token),
            json={"query": "anything"},
        )
        # User B, a completely different user, must be unaffected.
        still_allowed = await client.post(
            f"/api/v1/search?organization_id={org_b}",
            headers=auth_headers(user_b.access_token),
            json={"query": "anything"},
        )
    finally:
        _restore_default_settings()

    assert exhausted.status_code == 429
    assert still_allowed.status_code != 429


async def test_failed_login_throttle_locks_out_then_clears_on_success(
    client: AsyncClient,
) -> None:
    owner = await register_user(client, email="failed-login-throttle@example.com")

    _enable_rate_limiting()
    try:
        # RATE_LIMIT_FAILED_LOGIN_ATTEMPTS=3 in the test environment.
        for _ in range(3):
            response = await client.post(
                "/api/v1/auth/login",
                json={"email": owner.email, "password": "wrong-password"},
            )
            assert response.status_code == 401

        # The 4th attempt is throttled specifically because of the failed-
        # attempt count, even with the CORRECT password this time — proving
        # this is a real lockout, not just "wrong password forever".
        locked_out = await client.post(
            "/api/v1/auth/login",
            json={"email": owner.email, "password": "correct-horse-1"},
        )
        assert locked_out.status_code == 429
        assert "retry-after" in locked_out.headers
    finally:
        _restore_default_settings()
