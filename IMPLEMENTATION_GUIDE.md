# Implementation Guide

How this system is actually built: the architecture, the data model, and
the reasoning behind the real decisions made along the way. For how to run
it, see [`SETUP_GUIDE.md`](SETUP_GUIDE.md) and
[`EXECUTION_GUIDE.md`](EXECUTION_GUIDE.md).

This project was built incrementally, phase by phase, each with a real,
working implementation — no stubbed features — and its own recorded
design decisions in [`docs/adr/`](docs/adr/). This guide is a synthesis of
those decisions; where it summarizes, the linked ADR has the full
reasoning and trade-offs. [`PLAN.md`](PLAN.md) has the complete, honest
list of what's built versus deliberately deferred and why.

---

## 1. What this is

An enterprise knowledge and workflow platform: organizations upload
documents, ask questions grounded in them (with real, verifiable
citations), and can delegate multi-step tasks to an agent — which can
search, calculate, query data, draft communications, or take a
destructive action, but only after a human explicitly approves anything
genuinely risky.

## 2. Technology stack

| Layer | Choice | Why (ADR) |
|---|---|---|
| Backend framework | FastAPI (Python 3.12) | — |
| Database | PostgreSQL 16 | `ADR-001-database-choice.md` |
| Vector search | pgvector (in Postgres, not a separate vector DB) | `ADR-002-vector-search.md` |
| Background jobs | arq (Redis-backed) | `ADR-007-background-worker.md` |
| Embeddings | sentence-transformers, local | `ADR-008-embedding-provider.md` |
| Reranking | cross-encoder, local | `ADR-009-reranking.md` |
| LLM | Provider-abstracted — Ollama (local) or Anthropic | `ADR-004`, `ADR-010` |
| Frontend | Next.js 16 (App Router), TypeScript, Tailwind | `ADR-015-frontend-architecture.md` |
| Data fetching | TanStack Query, types generated from the live OpenAPI schema | `ADR-015` |
| Observability | Structured JSON logs + Prometheus metrics | `ADR-014-observability.md` |
| Deployment | Docker Compose (5 services) | `ADR-019-docker-compose.md` |

## 3. High-level architecture

```
+-------------+      +------------------+      +-------------+
|  Next.js    |----->|  FastAPI (api)   |----->|  PostgreSQL |
|  frontend   |<-----|                  |<-----|  + pgvector |
+-------------+      +--------+---------+      +-------------+
                              |  enqueues jobs
                              v
                       +--------------+          +-------------+
                       |  Redis       |<-------->|  arq worker |
                       | (queue +     |          | (document   |
                       |  rate limits)|          |  processing)|
                       +--------------+          +-------------+
```

The `api` and `worker` processes share the same backend codebase and
Postgres database — `worker` just runs a different entrypoint
(`arq app.workers.settings.WorkerSettings` instead of `uvicorn`), and
handles the one genuinely slow, blocking operation (document text
extraction/OCR/chunking/embedding) off the request path.

Everything else — including agent runs and chat, both of which can
involve real LLM calls — runs synchronously within the HTTP request
(`ADR-012`, decision on why this isn't also backgrounded: simpler failure
modes and a bounded runtime, at the cost of the request blocking for up to
`AGENT_MAX_RUNTIME_SECONDS`, 90s by default).

## 4. Directory structure

```
backend/
  app/
    api/v1/          One router module per resource (auth, documents,
                      search, conversations, agents, tools, admin, ...) -
                      router.py aggregates them all; read it first for a
                      map of the full API surface.
    core/             Cross-cutting concerns: config, logging, metrics,
                      rate limiting, security (JWT/password hashing),
                      request-correlation context, file validation, LLM
                      pricing estimates.
    models/           SQLAlchemy ORM models - one file per table.
    repositories/     Data-access layer between models and services -
                      each repository owns the queries for one aggregate.
    schemas/          Pydantic request/response models.
    services/         Business logic. agents/ and llm/ are their own
                      sub-packages (see S6/S7 below); embeddings/ and
                      reranking/ hold provider abstractions.
    workers/          The arq worker's task definitions and settings.
    main.py           App wiring: middleware order, exception handlers,
                      /metrics endpoint.
  migrations/         Alembic migrations, one per schema change.
  evaluation/         The offline RAG/agent quality evaluation framework
                      (separate from pytest - see S9).
  tests/              pytest suite, one file per resource/concern.
frontend/
  app/                Next.js App Router pages. (app)/ is the
                      authenticated route group (its own layout with the
                      sidebar); login/register sit outside it.
  components/         Shared UI: badges, cards, the citation chip.
  lib/api/            Generated types (schema.d.ts, from the live OpenAPI
                      schema - regenerate after backend changes, don't
                      hand-edit), the fetch client, and TanStack Query hooks.
  lib/auth/           Auth and current-organization React contexts.
docs/adr/             One file per real architecture decision, numbered
                      in the order made.
scripts/              backup.sh / restore.sh.
```

## 5. Data model

17 tables, all tenant-scoped by `organization_id` except where noted
(`ADR-006-multi-tenancy.md` — shared-schema multi-tenancy, not
schema-per-tenant or database-per-tenant):

- **Identity**: `organizations`, `users`, `memberships` (the join table
  carrying each user's *role* within an org — `viewer`/`employee`/
  `manager`/`admin`), `refresh_tokens`.
- **Knowledge base**: `collections`, `documents`, `document_chunks`
  (each chunk carries both a pgvector embedding *and* a `tsvector` column
  — hybrid semantic+keyword search, `ADR-002`).
- **Conversations**: `conversations`, `messages`, `citations` (each
  citation row links a specific answer to the specific chunk it came
  from — what makes the frontend's citation chips real, not decorative).
- **Agents**: `agent_runs`, `agent_steps`, `tool_calls`, `approvals` —
  every state transition and tool call an agent makes is persisted, not
  just the final answer, so a run is fully inspectable after the fact.
- **Evaluation**: `evaluation_runs`, `evaluation_results` — populated by
  `python -m evaluation.run`, not tenant-scoped in the usual sense (see
  §9 and `ADR-018-admin-dashboard.md` decision 2).

## 6. Document ingestion

`POST /api/v1/documents` validates the upload (size, MIME type sniffed
via libmagic, not just trusting the filename extension — `core/file_validation.py`),
stores the raw file, and enqueues a background job — the endpoint returns
immediately with the document in `pending` status. The worker then:

1. Extracts text (`services/extraction.py`) — format-specific (PDF,
   DOCX, XLSX, PPTX), with a real Tesseract OCR fallback for scanned PDFs
   with no extractable text layer.
2. Chunks the text (`services/chunking.py`).
3. Generates an embedding per chunk (`services/embeddings/`) and a
   `tsvector` for keyword search.
4. Marks the document `completed` — or `failed`, with the reason stored,
   if any step raised.

## 7. Search and RAG

`SearchService` (`services/search_service.py`) does hybrid retrieval:
semantic similarity (pgvector cosine distance) and keyword relevance
(Postgres full-text search via `tsvector`) are combined with a weighted
score (`hybrid_search_alpha`/`hybrid_search_beta`, configurable), then
optionally reranked by a cross-encoder before the top-K results are
returned.

`RagService` (`services/rag_service.py`) builds on top of search: fits
the retrieved chunks into a character budget, constructs a prompt that
keeps system instructions, conversation history, and retrieved content in
clearly separated sections (a real prompt-injection mitigation, not just
a hope — retrieved document content is never treated as instructions),
calls the LLM, and validates every citation the model claims against the
chunks it was actually given before returning the answer — a citation
number that doesn't correspond to a real, provided chunk is dropped, not
trusted.

## 8. The agent system

A deterministic state machine (`ADR-005`/`ADR-012`), not a black-box
agent loop — every transition (`planning` → `tool_selection` →
`tool_execution` → `observation` → `verification`, looping until the
goal is satisfied or a limit is hit) is a real, persisted `AgentStep` row.

**Tools** (`services/agents/tools/`): `search_documents`, `get_document`,
`calculate`, `generate_report`, `run_safe_sql` (a real, narrow read-only
SQL tool with a four-layer defense — see `ADR-012` — not a general SQL
executor), `draft_email`, and `delete_document`. Each tool declares its
own `risk_level` (`low`/`medium`/`high`).

**Human approval**: a `high`-risk tool call doesn't execute — it creates
a persisted `Approval` row and the run pauses in `awaiting_approval`
status. Nothing runs until a human explicitly calls
`POST /api/v1/agents/approvals/{id}/approve` (or `reject`) — this is
enforced at the service layer, not just hinted at in the UI, so there's
no way to bypass it by calling the API directly either.

## 9. Evaluation framework

Deliberately separate from the pytest suite (`ADR-011`): pytest proves
the *code* behaves correctly using fake LLM/embedding providers (fast,
deterministic, no external dependencies); the evaluation framework proves
*answer quality* using real providers against a fixed golden dataset —
retrieval recall, citation precision, and (for agents) task success rate,
tool selection accuracy, and unnecessary-tool-call rate. Results persist
to `evaluation_runs`/`evaluation_results` and are browsable in the admin
dashboard (`ADR-018`) — genuinely platform-wide, not scoped to any one
organization, since evaluation data belongs to a system-level dataset,
not a customer.

## 10. Observability, rate limiting, and admin access

- **Observability** (`ADR-014`): every log line and metric carries
  `request_id`/`user_id`/`organization_id` via `contextvars`, propagated
  correctly across the API↔worker process boundary. Metrics are real
  Prometheus counters/histograms, exposed at `/metrics` — a live snapshot
  of the current process, not a historical time series (no Prometheus
  server is actually deployed to poll and store these — `ADR-018`
  decision 3).
- **Rate limiting** (`ADR-017`): Redis-backed fixed-window counters,
  applied per-route (not a blanket middleware, since a chat request and a
  health check have very different real costs), plus a separate,
  tighter failed-login throttle keyed by *email* rather than IP — genuine
  protection against credential stuffing spread across many source IPs.
- **Admin access** (`ADR-018` decision 1): this app has no separate
  platform-admin role — "holds `admin` in at least one organization" is
  used as the trust proxy for viewing platform-wide operational data, a
  stated scope decision rather than a full platform-admin system.

## 11. Frontend architecture

Client-rendered (`"use client"` throughout), not RSC-heavy — the backend
authenticates via bearer JWT, not cookies, so React Server Components'
usual cookie-based auth model doesn't fit without adding infrastructure
this project doesn't need at its current scale (`ADR-015` decision 1).
Types come from `openapi-typescript`, generated directly against the
backend's live `/openapi.json` — not hand-written, so they can't silently
drift from what the API actually returns. TanStack Query handles all
server-state caching; two React contexts (`lib/auth/`) hold the
authenticated user and the currently-selected organization.

The design system (`ADR-015` decision 5) is deliberately tied to the
product's actual differentiator — grounded, cited answers — rather than a
generic AI-product look: a cool ink/paper palette with a single,
narrowly-scoped amber accent reserved *only* for citations, and an
interactive citation chip (expands to the real source excerpt) as the
one deliberate, product-specific design risk.

## 12. Security posture

Password hashing via Argon2 (`argon2-cffi`), JWT access + refresh tokens,
role-based access control enforced at the dependency-injection layer
(`api/v1/deps.py`'s `require_roles`), tenant isolation enforced by every
query being scoped to `organization_id` (never trusting a client-supplied
ID without checking membership first). Security headers on both backend
and frontend, a startup guard refusing to run in production with a
default JWT secret, and a real dependency-vulnerability audit with zero
known CVEs as of the last check — all `ADR-020`. Deliberately *not* yet
covered: a Content-Security-Policy (needs its own careful pass) and a
real secrets manager beyond a plain `.env` file (needs infrastructure
this project doesn't run) — both stated honestly in `PLAN.md`, not
silently skipped.

## 13. Where to go deeper

Every design decision summarized above has a full ADR with the actual
trade-offs considered, not just the conclusion — start at
[`docs/adr/`](docs/adr/) for anything this guide only touched briefly.
[`PLAN.md`](PLAN.md) has the complete, phase-by-phase history and the
honest current list of what's deliberately out of scope.
