# Execution Guide

Day-to-day commands for running, testing, and operating this system, once
it's [set up](SETUP_GUIDE.md). For what's actually happening under the
hood, see [`IMPLEMENTATION_GUIDE.md`](IMPLEMENTATION_GUIDE.md).

---

## Starting and stopping

### Docker Compose

```bash
docker compose up -d          # start everything in the background
docker compose logs -f api    # follow one service's logs
docker compose ps             # check status/health of every service
docker compose down           # stop everything
docker compose down -v        # stop and also delete the postgres/upload volumes
```

### Manual (five separate processes)

Each in its own terminal, from the repo root:

```bash
# 1. Postgres and Redis (if not already running as system services)
sudo service postgresql start
sudo service redis-server start

# 2. API
cd backend && source .venv/bin/activate
uvicorn app.main:app --reload --port 8000

# 3. Background worker — required for document uploads to actually
#    process; without this, uploads stay stuck on "pending" forever
cd backend && source .venv/bin/activate
arq app.workers.settings.WorkerSettings

# 4. Frontend
cd frontend && npm run dev
```

Stopping: `Ctrl+C` each process. Uvicorn and Next.js both handle `Ctrl+C`
(SIGINT) gracefully; the worker does too, though its graceful-shutdown
window (`job_completion_wait = 30` seconds, see
`docs/adr/ADR-020-production-readiness.md` decision 6) only matters if a
document is actively being processed at the moment you stop it.

---

## Using the app

A walkthrough of the real, working features, roughly in the order you'd
naturally use them:

1. **Register** (`/register`) — creates your account *and* your first
   organization, with you as its `admin`. Every subsequent thing you do is
   scoped to an organization; if you're ever added to a second one, a
   switcher appears in the sidebar.
2. **Upload documents** (`/documents`) — PDF, DOCX, XLSX, PPTX, TXT, MD,
   or CSV. Status moves `pending` → `processing` → `completed` as the
   background worker extracts text (with OCR fallback for scanned PDFs),
   chunks it, and generates embeddings. `failed` documents show why.
3. **Chat** (`/chat`) — ask questions grounded in your uploaded documents.
   Every answer that cites a source shows an interactive citation chip —
   click it to see the actual excerpt it came from, not just a bracketed
   number.
4. **Agents** (`/agents`) — give the agent a goal in plain language. It
   can search your documents, do calculations, run safe read-only SQL
   queries, draft an email, generate a report, or delete a document. The
   first several are low/medium risk and run automatically; deleting a
   document is high-risk and pauses for your explicit approval before it
   happens — reviewable in the run's detail page.
5. **Admin** (`/admin`, visible only if you hold `admin` in at least one
   organization) — a live snapshot of request/error/latency/cost metrics
   since the server last started, plus a browsable history of every
   evaluation run (see below).

---

## Tests and quality gates

### Backend

```bash
cd backend && source .venv/bin/activate

pytest                        # full suite — needs Postgres AND Redis running
pytest tests/test_agents_api.py -v      # a single file
pytest -k "rate_limit"                  # tests matching a keyword

ruff check .                  # lint
ruff format .                 # auto-format
mypy app evaluation           # strict type checking
```

The test suite creates and tears down its own tables in a separate test
database (`enterprise_ai_platform_test`, Redis DB index 15) — it won't
touch your dev data.

### Frontend

```bash
cd frontend

npx tsc --noEmit               # typecheck
npm run lint                   # eslint
npm run build                  # production build (also re-typechecks)
```

There's no frontend unit-test suite — verification here has leaned on
`tsc`/`eslint`/`build` plus direct HTTP checks against a real running
backend (see `docs/adr/ADR-015-frontend-architecture.md` and later
frontend-phase ADRs for why: genuine browser-based E2E testing wasn't
achievable in the sandbox this project was built in, `cdn.playwright.dev`
being network-blocked there).

### Dependency vulnerability scans

```bash
cd backend && pip install pip-audit && pip-audit -r requirements.txt
cd frontend && npm audit
```

Worth running periodically, not just once — see
`docs/adr/ADR-020-production-readiness.md` for the audit methodology used
when this was last done.

---

## Running the evaluation framework

Separate from the pytest suite — this measures actual RAG/agent *quality*
(retrieval recall, citation precision, agent task success rate) against a
fixed golden dataset, not just "does the code run without crashing":

```bash
cd backend && source .venv/bin/activate
python -m evaluation.run
```

Requires a real, reachable embedding provider and LLM (unlike the pytest
suite, which uses fakes for these by design — see
`docs/adr/ADR-011-evaluation-framework.md`). Results are persisted to the
`evaluation_runs`/`evaluation_results` tables and browsable afterward at
`/admin/evaluations` in the frontend, or via
`GET /api/v1/admin/evaluations`.

---

## Observability

- **Structured logs**: JSON to stdout from every process (api, worker),
  each line carrying `request_id`/`user_id`/`organization_id` where
  applicable — `docker compose logs -f api` or your terminal for the
  manual path.
- **Prometheus metrics**: `GET http://localhost:8000/metrics` — raw
  Prometheus text format, cumulative since the process started (not a
  historical time series; there's no Prometheus server actually running
  to poll and store these — see `docs/adr/ADR-018-admin-dashboard.md`
  decision 3). The same data in a friendlier JSON summary:
  `GET /api/v1/admin/metrics-summary` (admin-only), or the `/admin`
  frontend page.

---

## Backup and restore

Requires the Docker Compose stack (these scripts shell out to
`docker compose exec postgres ...`):

```bash
./scripts/backup.sh                          # writes ./backups/enterprise_ai_platform-<timestamp>.sql.gz
./scripts/restore.sh path/to/backup.sql.gz    # destructive — asks you to type the DB name to confirm
```

See `docs/adr/ADR-020-production-readiness.md` decision 8 for exactly
what's verified about these (the underlying SQL was tested end to end;
the Docker wrapper around it wasn't, for the same reason
`docker compose up --build` itself wasn't — see the note in
`SETUP_GUIDE.md`).

---

## Troubleshooting common runtime issues

| Symptom | Where to look |
|---|---|
| A request returns `429 Too Many Requests` | Expected behavior — rate limiting (`docs/adr/ADR-017-rate-limiting.md`). The response's `Retry-After` header and JSON body both say how long to wait. |
| An agent run says `"status": "failed"` with a planner/connection error | No LLM provider is actually reachable — check `LLM_PROVIDER` and that Ollama/Anthropic is configured (same as the setup guide's chat troubleshooting) |
| A document is stuck on `processing` for a long time | Check the worker's own logs — extraction/OCR on a large or scanned PDF can genuinely take a while; `job_timeout = 300` (5 minutes) is the hard cap before it's marked `failed` |
| `docker compose ps` shows a service as `unhealthy` | `docker compose logs <service>` — for `api`, this is often a migration failure (check `DATABASE_URL`) or a missing/insecure `JWT_SECRET` in production mode |
| The app won't start, error mentions the default JWT secret | You're running with `ENVIRONMENT=production` — see the Setup Guide's troubleshooting table |
