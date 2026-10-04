# ADR-007: Background Worker Library

**Status:** Accepted

## Context
Document ingestion (validation already done synchronously in the request, but
extraction/OCR/eventually chunking+embedding) must not run in the HTTP request
path (spec §11). Need a background job system backed by Redis (already chosen
for caching — see CLAUDE.md stack).

## Decision
`arq` — a minimal async job queue built directly on `asyncio` and Redis.

## Alternatives considered
**Celery** — the default choice for many Python projects, but:
- Celery's core execution model is synchronous-worker-first; async task support
  exists but is bolted on, not native. This project's DB layer, HTTP layer, and
  LLM provider calls are async throughout (see ADR-004) — a sync-first task
  runner would mean either blocking the event loop inside tasks or maintaining
  a separate sync DB session path just for workers.
- Brings a much larger surface (multiple broker backends, routing, Flower for
  monitoring, its own configuration DSL) than this project needs at this scale
  — CLAUDE.md §60 explicitly calls out preferring simple+reliable over
  complex+impressive.

## Reasoning
- `arq` tasks are plain `async def` functions — the same SQLAlchemy async
  session factory, the same `Settings`, the same code patterns as the API
  layer. No parallel sync/async split to maintain.
- Already depends only on Redis, which the project already requires.
- Small enough to read end-to-end when debugging a stuck job — matters for a
  portfolio project meant to be inspected, not just run.

## Trade-offs
- Smaller ecosystem than Celery (no built-in web monitoring UI, fewer routing
  features). Acceptable — job routing/prioritization needs here are minimal
  (one queue, a handful of task types), and admin visibility into job status
  is provided by the `documents.status` field itself, not a separate UI.
- Redis-only (no RabbitMQ/SQS backend option). Acceptable since Redis is
  already a required dependency for caching.

## Consequences
- Worker process is started with `arq app.workers.settings.WorkerSettings`,
  separate from the `uvicorn` API process — documented in CLAUDE.md §5.
- If task volume/complexity later genuinely outgrows arq (e.g. needs complex
  routing, multiple broker types, or a large monitoring UI), revisit with
  actual evidence, per §59 — not assumed up front.
