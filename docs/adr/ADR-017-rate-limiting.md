# ADR-017: Rate Limiting and Abuse Prevention (spec §39)

**Status:** Accepted

## Context
Deferred at least four times across Phases 4, 6, 10, and 13's slot going to
agent UI instead. With the frontend now covering the full core product
loop end-to-end (Phase 12/13), this protects a real, working system rather
than a partial one — the actual reason it was chosen as this phase over
admin/evaluation dashboards.

## Decision 1: Redis-backed fixed-window counters, not sliding-window-log
`INCR` + `EXPIRE` on a per-window key (`ratelimit:{scope}:{identifier}:
{window_start}`) — not a sorted-set sliding-window log (`ZADD`/
`ZREMRANGEBYSCORE`/`ZCARD`). Fixed windows have a known, real limitation:
a burst straddling the boundary between two adjacent windows can allow up
to roughly 2x the stated limit in a short span. Accepted as a reasonable
trade-off for this project's scope — the goal here is genuine abuse
prevention (stopping sustained hammering and credential-stuffing), not
precise rate-shaping — and a sliding-window-log implementation is real
additional complexity (unbounded-looking sorted-set growth needing careful
trimming, more Redis round-trips per check) that isn't justified until
there's evidence the boundary case matters in practice. A real upgrade
path if it ever does.

## Decision 2: a dedicated Redis connection, not arq's job-queue pool
`redis` (already installed transitively via `arq`, now declared explicitly
in `requirements.txt` since it's imported directly) gets its own lazy-
singleton connection (`app/core/rate_limit.py`), mirroring `app/db/
session.py`'s and `app/workers/queue.py`'s existing pattern. Reusing arq's
`ArqRedis` pool for unrelated counter operations would technically work
(`ArqRedis` is a real Redis client under the hood) but conflates two
genuinely separate concerns — the job queue and rate-limit counters — the
same way this project keeps `SearchService`/`RagService`/`AgentService`
separate despite all three using Postgres.

## Decision 3: identification is user_id where authenticated, client IP where not
Every rate-limited route already has a natural identity to key on:
`CurrentUser.id` for authenticated routes (upload, search, chat, agent
runs), `request.client.host` for the two routes that precede
authentication (`/auth/login`, `/auth/register`) — there is no user_id yet
at that point. `request.client.host` is used directly rather than trusting
an `X-Forwarded-For` header, since that header is trivially spoofable
without a trusted reverse proxy in front of this app stripping/setting it
correctly — a real deployment behind such a proxy would need to consume it
carefully, not blindly; noted here rather than implemented against an
assumption this project can't currently verify.

## Decision 4: failed-login throttling is a separate, tighter mechanism than the general route limit
A general per-IP limit on `/auth/login` (e.g. 20/minute) stops basic
hammering, but doesn't specifically protect one targeted account from
credential stuffing across many source IPs. A second counter — keyed by
the attempted *email*, incremented only when `AuthService.login` raises
`InvalidCredentialsError`, never on success — locks out further attempts
against that specific account after a small number of failures within a
window, independent of which IP each attempt came from. This is the
standard, correct shape for this protection: legitimate users making
several genuine login attempts from a shared IP (e.g. an office network)
aren't penalized by the general route limit's IP-based counting, while a
credential-stuffing attempt against one email is stopped regardless of how
many source IPs it's spread across.

## Decision 5: 429 responses match the existing error shape, plus a real Retry-After
`{"error": {"code": "RATE_LIMITED", "message", "request_id"}}` — the same
shape every other error response already uses (Phase 2/6/11) — with a
`Retry-After` header set to the actual number of seconds until the current
window resets, not a hardcoded placeholder. `RATE_LIMIT_EXCEEDED` is a new
Prometheus counter (extending Phase 11's metrics, labeled by scope) and
every rejection logs a structured `rate_limit_exceeded` entry carrying the
same request-correlation context every other log line does.

## Decision 6: applied via an explicit per-route dependency, not a blanket middleware
A `rate_limit(scope, limit, window_seconds)` dependency factory, matching
the existing `require_roles(*allowed_roles)` factory pattern in `api/v1/
deps.py` — not a single global middleware applying one limit to everything.
Different endpoints have genuinely different real costs: a chat/agent call
triggers a real LLM request, a document upload consumes real storage, a
health check costs nothing. One blanket limit would either be too loose for
the expensive routes or too tight for cheap ones.

## Consequences
- Building this phase surfaced a real, pre-existing gap: `handle_http_exception`
  (Phase 2/6/11) had a comment claiming it "ensure[d] the response shape is
  consistent everywhere," but actually delegated to FastAPI's default handler,
  producing `{"detail": "..."}` for every plain `HTTPException` — not the
  `{"error": {"code", "message", "request_id"}}` shape every other error path
  used. Fixed properly (not routed around) once discovered: `handle_http_exception`
  now genuinely produces the consistent shape, preserving any custom headers
  the raising code attached (critical here, since `rate_limit.py` sets
  `Retry-After`, which would otherwise be silently dropped). Verified safe
  app-wide — zero existing tests depended on the old `detail` key — with the
  full suite (279 tests) passing after the change.
- That fix turned out to matter beyond rate limiting: the frontend's
  `ApiError` constructor (Phase 12) reads `body.error.message`
  unconditionally. Against the old `{"detail": ...}` shape, that access
  would throw inside the constructor itself — meaning every 401 (wrong
  password), 403, 404, and 409 response since Phase 12 was silently falling
  back to a generic frontend error message instead of the real one, on
  login, register, documents, and agent pages alike. This phase's backend
  fix retroactively resolves that cross-phase bug; no frontend code change
  was needed once the backend response shape was actually correct.
- Frontend's existing `ApiError` handling already surfaces any non-2xx
  response's message — a 429's `message` field is written to read
  naturally there (e.g. "Too many requests. Try again in 42 seconds.")
  without needing frontend-specific 429 handling beyond that, *now that*
  the backend genuinely delivers the shape it always claimed to.
- Rate limit thresholds are configurable via settings with sensible
  defaults, not hardcoded — tunable without a code change if real usage
  patterns turn out to need different numbers.
