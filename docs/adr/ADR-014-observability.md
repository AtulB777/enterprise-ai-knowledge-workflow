# ADR-014: Observability — Request Correlation, Metrics, and Tracing Scope

**Status:** Accepted

## Context
Spec §29 requires structured logs carrying a specific field list (request ID,
user ID, tenant ID, endpoint, latency, model, token usage, retrieval
latency, LLM latency, tool calls, errors), named Prometheus-style metrics
(REQUEST_COUNT, ERROR_COUNT, LATENCY, TOKEN_USAGE, MODEL_COST,
RETRIEVAL_LATENCY, LLM_LATENCY, AGENT_STEPS), and "tracing where practical."
Phase 2's `app/core/logging.py` deliberately left request-scoped fields for
this phase (see its own docstring) — the JSON formatter existed, but
nothing populated request_id/user_id/tenant_id on every log line, and
nothing logged successful requests at all (only the three exception
handlers each minted their own throwaway `request_id`, discarded on every
successful request and inconsistent with any client-supplied correlation
ID).

## Decision 1: contextvars-based request correlation, not per-call `extra=`
A single middleware generates (or honors an incoming `X-Request-ID` header)
one request_id per request, binds it to a `contextvars.ContextVar`, and a
`logging.Filter` injects it into every log record automatically — so any
`logger.info(...)` call anywhere during that request carries it without the
caller remembering to pass `extra={"request_id": ...}`. `user_id`/
`organization_id` are bound the same way, but by `get_current_user`/
`get_membership` in `api/v1/deps.py` at the moment they're actually
resolved — middleware runs before dependency injection, so it can't know
the caller's identity yet; binding at the auth-resolution point is both
correct (only known-authenticated requests get a user_id) and avoids
redundantly decoding the JWT a second time just for logging.

The three existing exception handlers (Phase 2/6) now read the *same*
request_id from context instead of minting their own — previously, an
error response's `request_id` could differ from what a client's own
`X-Request-ID` header asked for, which defeats the point of a correlation
ID.

## Decision 2: Prometheus client library, not a custom metrics format
`prometheus-client` — the standard library for exposing Prometheus-format
metrics from Python — is added as a real, single, well-established
dependency. `GET /metrics` is mounted at the application root, not under
`/api/v1`: it's operational infrastructure, not a versioned business API
resource, and root-level `/metrics` is the near-universal convention
Prometheus scrape configs default to. Deliberately unauthenticated, matching
standard practice — metrics endpoints are conventionally protected by
network-level controls (private network / firewall) in real deployments,
not application-level auth, since Prometheus's scrape model doesn't easily
support arbitrary custom authentication.

## Decision 3: "tracing where practical" means request-ID correlation across the API/worker boundary, not full OpenTelemetry
Full distributed tracing (OpenTelemetry SDK + exporter + collector) is
deliberately NOT implemented. Reasoning, not just convenience: distributed
tracing's core value is correlating spans *across service boundaries* — but
this system (CLAUDE.md's own architecture decision) is a modular monolith
plus one background worker, not a microservices topology. The one real
cross-process boundary that exists — an HTTP request enqueuing a
`process_document` job the worker picks up later — gets genuine, practical
correlation instead: the enqueuing request's request_id is passed as a job
argument, and the worker binds it into its own logging context for that
job's entire execution. Grepping logs for one request_id now surfaces both
the original upload request AND the worker's subsequent processing of it,
which is the actual, practical benefit tracing would provide here, without
adding an exporter/collector nobody would query for a 2-process system.
**If a genuine multi-service topology emerges later, this should be
revisited with actual evidence, per CLAUDE.md §59 — not assumed now.**

## Decision 4: MODEL_COST needed a pricing table that never got built (Phase 8 gap, fixed here)
ADR-011 (Phase 8) planned "a configurable pricing table... rather than
hardcoding figures presented as authoritative" for evaluation cost
estimates, but the evaluation runner's per-case `metrics` dict never
actually included token usage or cost — not because a field was silently
left at a default (Phase 8's actual accepted model uses a flexible JSONB
`metrics` dict by design, not individual columns; there was never a
dedicated `estimated_cost_usd` column to leave unset), but because
`RagAnswer` didn't expose the underlying LLM call's token counts to its
caller at all — they were a local variable trapped inside
`RagService.ask()`. Since Phase 11 needs real cost estimation for the
MODEL_COST metric anyway, `app/core/pricing.py` implements it now (a small
table of approximate $/million-token rates, explicitly commented as needing
verification against each provider's current published pricing — same
principle as ADR-011, applied to where it was actually supposed to land),
and `RagAnswer` gained `model`/`input_tokens`/`output_tokens` fields so the
evaluation runner (and any other caller) can finally access what a RAG
answer actually cost, closing the real structural gap rather than the one
originally (and incorrectly) assumed.

## Consequences
- Every tool call, LLM call, and retrieval operation now emits a
  latency/count observation — genuinely inspectable via `/metrics`, not
  just documented as a goal.
- Logs never include secrets: the existing `JsonFormatter` redaction (Phase
  2) already drops password/api_key/token/secret-named fields; the new
  contextvar-injected fields (request_id, user_id, organization_id) are
  identifiers, never credentials, so this required no change to the
  redaction logic itself, only verification that it still applies.
