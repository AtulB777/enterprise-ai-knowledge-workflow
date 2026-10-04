"""Tests for the core fixed-window rate-limit counting logic against real
Redis (test DB 15, see conftest.py) — no fakes, matching this project's
established testing philosophy for Postgres/Redis throughout.
"""

import asyncio

import redis.asyncio as redis

from app.core.config import get_settings
from app.core.rate_limit import check_rate_limit


async def _get_test_redis() -> redis.Redis:
    settings = get_settings()
    return redis.from_url(settings.redis_url, decode_responses=True)


async def test_allows_requests_under_the_limit() -> None:
    client = await _get_test_redis()
    for _ in range(3):
        result = await check_rate_limit(
            client=client, scope="test-under", identifier="user-1", limit=5, window_seconds=60
        )
        assert result.allowed is True


async def test_rejects_requests_over_the_limit() -> None:
    client = await _get_test_redis()
    for _ in range(3):
        result = await check_rate_limit(
            client=client, scope="test-over", identifier="user-2", limit=3, window_seconds=60
        )
        assert result.allowed is True

    # The 4th request within the same window must be rejected.
    result = await check_rate_limit(
        client=client, scope="test-over", identifier="user-2", limit=3, window_seconds=60
    )
    assert result.allowed is False
    assert result.remaining == 0
    assert result.retry_after_seconds > 0


async def test_remaining_count_decreases_correctly() -> None:
    client = await _get_test_redis()
    first = await check_rate_limit(
        client=client, scope="test-remaining", identifier="user-3", limit=5, window_seconds=60
    )
    second = await check_rate_limit(
        client=client, scope="test-remaining", identifier="user-3", limit=5, window_seconds=60
    )
    assert first.remaining == 4
    assert second.remaining == 3


async def test_different_identifiers_have_independent_counters() -> None:
    client = await _get_test_redis()
    for _ in range(3):
        await check_rate_limit(
            client=client,
            scope="test-independent",
            identifier="user-a",
            limit=3,
            window_seconds=60,
        )
    # user-a is now exhausted, but a completely different identifier in the
    # same scope must have its own, unaffected counter.
    result = await check_rate_limit(
        client=client, scope="test-independent", identifier="user-b", limit=3, window_seconds=60
    )
    assert result.allowed is True
    assert result.remaining == 2


async def test_different_scopes_have_independent_counters_for_the_same_identifier() -> None:
    client = await _get_test_redis()
    for _ in range(3):
        await check_rate_limit(
            client=client, scope="scope-a", identifier="same-user", limit=3, window_seconds=60
        )
    # Same identifier, different scope (e.g. "upload" vs "search") — must
    # not share a counter just because the caller is the same.
    result = await check_rate_limit(
        client=client, scope="scope-b", identifier="same-user", limit=3, window_seconds=60
    )
    assert result.allowed is True
    assert result.remaining == 2


async def test_new_window_resets_the_counter() -> None:
    """Proves the window actually rolls over, using a 1-second window and
    waiting for it to pass — a real, not simulated, time-based check.
    """
    client = await _get_test_redis()
    for _ in range(2):
        result = await check_rate_limit(
            client=client, scope="test-window", identifier="user-4", limit=2, window_seconds=1
        )
        assert result.allowed is True

    exhausted = await check_rate_limit(
        client=client, scope="test-window", identifier="user-4", limit=2, window_seconds=1
    )
    assert exhausted.allowed is False

    await asyncio.sleep(1.2)

    fresh_window = await check_rate_limit(
        client=client, scope="test-window", identifier="user-4", limit=2, window_seconds=1
    )
    assert fresh_window.allowed is True
