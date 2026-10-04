"""Redis-backed rate limiting (spec §39, ADR-017). A dedicated connection —
not arq's job-queue pool (ADR-017 decision 2) — using fixed-window counters
(ADR-017 decision 1: simpler than a sliding-window log, with a documented,
accepted boundary-burst trade-off).
"""

import hashlib
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated

import redis.asyncio as redis
from fastapi import Depends, HTTPException, Request, status

from app.core.config import Settings, get_settings
from app.core.metrics import RATE_LIMIT_EXCEEDED
from app.core.request_context import get_request_id

logger = logging.getLogger("app.rate_limit")

_client: redis.Redis | None = None


async def get_rate_limit_redis() -> redis.Redis:
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.redis_url:
            raise RuntimeError(
                "REDIS_URL is not configured. Set it in .env before using rate limiting."
            )
        # redis-py's async module doesn't ship a fully typed stub for
        # from_url in the installed version — a real gap in the library's
        # own typing, not something to work around by weakening our types.
        _client = redis.from_url(settings.redis_url, decode_responses=True)  # type: ignore[no-untyped-call]
    return _client


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after_seconds: int


async def check_rate_limit(
    *, client: redis.Redis, scope: str, identifier: str, limit: int, window_seconds: int
) -> RateLimitResult:
    """Increments the counter for this scope/identifier/current-window and
    reports whether the caller is still within `limit`. The window boundary
    is a fixed multiple of `window_seconds` since the epoch, not a rolling
    window from each caller's first request — see ADR-017 decision 1 for
    why that's an accepted trade-off here.
    """
    now = int(time.time())
    window_start = now - (now % window_seconds)
    key = f"ratelimit:{scope}:{identifier}:{window_start}"

    count = await client.incr(key)
    if count == 1:
        # Only set the TTL on the first increment in this window — resetting
        # it on every call would let a sustained caller keep the key alive
        # indefinitely and never actually roll over to a fresh window.
        await client.expire(key, window_seconds)

    retry_after = window_start + window_seconds - now
    if count > limit:
        return RateLimitResult(allowed=False, remaining=0, retry_after_seconds=retry_after)
    return RateLimitResult(allowed=True, remaining=limit - count, retry_after_seconds=retry_after)


def _raise_if_exceeded(result: RateLimitResult, *, scope: str, identifier: str) -> None:
    if result.allowed:
        return
    RATE_LIMIT_EXCEEDED.labels(scope=scope).inc()
    logger.warning(
        "rate_limit_exceeded",
        extra={"scope": scope, "identifier": identifier, "request_id": get_request_id()},
    )
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=(
            f"Too many requests. Try again in {result.retry_after_seconds} second"
            f"{'s' if result.retry_after_seconds != 1 else ''}."
        ),
        headers={"Retry-After": str(result.retry_after_seconds)},
    )


def rate_limit_by_ip(
    scope: str, *, limit: int, window_seconds: int
) -> Callable[..., Awaitable[None]]:
    """For routes that run before authentication resolves (login, register)
    — see ADR-017 decision 3. `request.client.host` directly, not
    `X-Forwarded-For`: that header is trivially spoofable without a trusted
    reverse proxy in front of this app to strip/set it correctly, which
    this project has no way to verify exists.
    """

    async def _check(
        request: Request, settings: Annotated[Settings, Depends(get_settings)]
    ) -> None:
        if not settings.rate_limiting_enabled:
            return
        client_host = request.client.host if request.client else "unknown"
        identifier = f"ip:{client_host}"
        redis_client = await get_rate_limit_redis()
        result = await check_rate_limit(
            client=redis_client,
            scope=scope,
            identifier=identifier,
            limit=limit,
            window_seconds=window_seconds,
        )
        _raise_if_exceeded(result, scope=scope, identifier=identifier)

    return _check


def rate_limit_by_user(
    scope: str, *, limit: int, window_seconds: int
) -> Callable[..., Awaitable[None]]:
    """For authenticated routes — keys on the real, JWT-verified user_id via
    FastAPI's own dependency chaining (depends on `get_current_user`, the
    same dependency every protected route already uses), rather than
    re-decoding the token here and duplicating that verification logic.
    """
    # Imported inside the factory, not at module level: app.api.v1.deps
    # doesn't import from this module, so there's no real circular-import
    # risk, but keeping it local makes the one-directional dependency
    # explicit rather than accidental.
    from app.api.v1.deps import CurrentUser

    async def _check(
        current_user: CurrentUser, settings: Annotated[Settings, Depends(get_settings)]
    ) -> None:
        if not settings.rate_limiting_enabled:
            return
        identifier = f"user:{current_user.id}"
        redis_client = await get_rate_limit_redis()
        result = await check_rate_limit(
            client=redis_client,
            scope=scope,
            identifier=identifier,
            limit=limit,
            window_seconds=window_seconds,
        )
        _raise_if_exceeded(result, scope=scope, identifier=identifier)

    return _check


# --- Failed-login throttling (ADR-017 decision 4) ---
#
# A separate, tighter mechanism from the general rate_limit_by_ip on
# /auth/login above: keyed by the attempted *email*, not the caller's IP,
# and incremented only on a genuinely failed password check — protecting
# one targeted account against credential stuffing spread across many
# source IPs, which the general per-IP route limit can't do.

_FAILED_LOGIN_SCOPE = "failed-login"


async def check_failed_login_throttle(email: str, *, settings: Settings) -> RateLimitResult:
    """Read-only check — does not increment. Call before attempting password
    verification, so an already-locked-out account doesn't pay the cost of
    a password hash comparison it can't succeed at anyway.

    This is the actual enforcement point once an account is throttled: every
    attempt after the one that first hit the limit gets intercepted here,
    before ever reaching record_failed_login() again — so the metric/log for
    a rejected attempt belongs here, not in record_failed_login's own
    (in-practice unreachable, once already throttled) rejection handling.
    """
    if not settings.rate_limiting_enabled:
        return RateLimitResult(
            allowed=True,
            remaining=settings.rate_limit_failed_login_attempts,
            retry_after_seconds=0,
        )
    client = await get_rate_limit_redis()
    now = int(time.time())
    window_seconds = settings.rate_limit_failed_login_window_seconds
    window_start = now - (now % window_seconds)
    key = f"ratelimit:{_FAILED_LOGIN_SCOPE}:{email.lower()}:{window_start}"
    raw_count = await client.get(key)
    count = int(raw_count) if raw_count is not None else 0
    retry_after = window_start + window_seconds - now
    limit = settings.rate_limit_failed_login_attempts

    if count >= limit:
        RATE_LIMIT_EXCEEDED.labels(scope=_FAILED_LOGIN_SCOPE).inc()
        logger.warning(
            "failed_login_throttle_engaged",
            extra={
                # A stable one-way hash, not the raw email (avoid logging
                # PII unnecessarily) and not Python's built-in hash() (its
                # per-process randomization would make repeated attempts
                # against the same account un-correlatable across restarts).
                "email_hash": hashlib.sha256(email.lower().encode()).hexdigest()[:16],
                "request_id": get_request_id(),
            },
        )
        return RateLimitResult(allowed=False, remaining=0, retry_after_seconds=retry_after)
    return RateLimitResult(allowed=True, remaining=limit - count, retry_after_seconds=retry_after)


async def record_failed_login(email: str, *, settings: Settings) -> None:
    """Increments the failed-attempt counter after a genuine wrong-password
    event. Deliberately doesn't duplicate the rejection metric/log — see
    check_failed_login_throttle's docstring for why that lives there instead.
    """
    if not settings.rate_limiting_enabled:
        return
    client = await get_rate_limit_redis()
    await check_rate_limit(
        client=client,
        scope=_FAILED_LOGIN_SCOPE,
        identifier=email.lower(),
        limit=settings.rate_limit_failed_login_attempts,
        window_seconds=settings.rate_limit_failed_login_window_seconds,
    )


async def clear_failed_login_throttle(email: str, *, settings: Settings) -> None:
    """Called on a successful login — a genuine login shouldn't stay
    partially penalized by earlier failed attempts once the account owner
    has actually proven who they are.
    """
    if not settings.rate_limiting_enabled:
        return
    client = await get_rate_limit_redis()
    now = int(time.time())
    window_seconds = settings.rate_limit_failed_login_window_seconds
    window_start = now - (now % window_seconds)
    key = f"ratelimit:{_FAILED_LOGIN_SCOPE}:{email.lower()}:{window_start}"
    await client.delete(key)
