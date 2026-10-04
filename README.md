# Enterprise AI Knowledge & Workflow Platform

Document intelligence, retrieval-augmented chat, and human-approval-gated
agent workflows for organizations — FastAPI/Postgres/pgvector backend,
Next.js frontend, real background job processing.

This is a portfolio project built phase by phase, each with a real,
working implementation (no stubbed features) and its own design decisions
recorded in [`docs/adr/`](docs/adr/). [`PLAN.md`](PLAN.md) tracks what's
built, what's deliberately deferred, and why. [`CLAUDE.md`](CLAUDE.md) is
the fuller internal continuity/architecture reference.

Three focused guides cover the rest:
- [`SETUP_GUIDE.md`](SETUP_GUIDE.md) — from a fresh clone to a running environment
- [`EXECUTION_GUIDE.md`](EXECUTION_GUIDE.md) — day-to-day commands: running, testing, evaluating, operating
- [`IMPLEMENTATION_GUIDE.md`](IMPLEMENTATION_GUIDE.md) — how the system is actually architected and built

On Windows? Start with [`WINDOWS_GUIDE.md`](WINDOWS_GUIDE.md) instead —
it covers the Windows-specific parts (Docker Desktop, WSL2, PowerShell
syntax, and the real native-Windows gotchas) that the guides above don't.

## Quick start

```bash
cp .env.example .env    # at minimum, set a real JWT_SECRET
docker compose up --build
```

Frontend at http://localhost:3000, API at http://localhost:8000 once
healthy. See [`SETUP_GUIDE.md`](SETUP_GUIDE.md) for the manual
(no-Docker) path, LLM provider configuration, and troubleshooting; see
[`EXECUTION_GUIDE.md`](EXECUTION_GUIDE.md) for day-to-day commands
(tests, the evaluation framework, backup/restore, using the app).

## Project structure

```
backend/    FastAPI app, SQLAlchemy models, Alembic migrations, the
            evaluation framework (`python -m evaluation.run`)
frontend/   Next.js app (App Router, TypeScript, Tailwind)
docs/adr/   One file per real architecture decision, in the order made
scripts/    backup.sh / restore.sh
```

## Status

18 phases in, covering auth/RBAC, document ingestion (with real OCR),
hybrid retrieval + RAG with citations, an evaluation framework with
real metrics, a deterministic agent system with genuine human-approval
gating, observability (structured logs, Prometheus metrics), rate
limiting, a real frontend with an admin dashboard, Docker Compose, and a
production-readiness audit. See `PLAN.md` for the honest, current list of
what's deliberately deferred and why — this project treats "not yet
done, and here's the real reason" as a normal, expected state, not
something to hide.
