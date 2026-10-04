# Setup Guide

Getting this project from a fresh clone to a running environment. If you
just want to *run* the app rather than develop on it, [Docker Compose](#path-a-docker-compose-recommended)
is the fastest path. If you're going to work on the code, see
[Manual Setup](#path-b-manual-setup-for-active-development).

For what to do *after* setup — starting/stopping services day to day,
running tests, using the app — see [`EXECUTION_GUIDE.md`](EXECUTION_GUIDE.md).
For how the system is actually built, see [`IMPLEMENTATION_GUIDE.md`](IMPLEMENTATION_GUIDE.md).

---

## Prerequisites

| Path | You need |
|---|---|
| Docker Compose | Docker Engine with Compose v2 (`docker compose version` should work) |
| Manual | Python 3.12, Node.js 22, PostgreSQL 16 with the [pgvector](https://github.com/pgvector/pgvector) extension, Redis 7 |

Either path also needs an LLM to actually answer questions or run agents:
either [Ollama](https://ollama.com) running locally, or an Anthropic API
key. Everything else (auth, document upload, search) works without one —
only chat and agent runs need a real LLM.

---

## Path A: Docker Compose (recommended)

```bash
git clone <this-repo>
cd <this-repo>
cp .env.example .env
```

Open `.env` and set at minimum:

```bash
JWT_SECRET=<run: openssl rand -hex 32>
ENVIRONMENT=development   # the app refuses to start with the default
                           # JWT_SECRET if this is "production" — see
                           # docs/adr/ADR-020-production-readiness.md
```

Decide on an LLM provider (see [Choosing an LLM provider](#choosing-an-llm-provider)
below), then:

```bash
docker compose up --build
```

First run downloads base images and builds both application images, which
takes a few minutes — subsequent runs are much faster. The `api` service
runs database migrations automatically on startup before it starts
serving.

Once everything is healthy:

- Frontend: http://localhost:3000
- API: http://localhost:8000 (interactive docs at `/docs`)

Jump to [Verifying your setup](#verifying-your-setup) below.

> **A note on this environment's own sandbox**: this project was built in
> a sandbox where Docker's own package registry (`registry-1.docker.io`)
> is network-blocked, so `docker compose up --build` was never actually
> run end-to-end there — only `docker compose config` (structural
> validation) was possible. See `docs/adr/ADR-019-docker-compose.md` for
> exactly what was and wasn't verified. On a normal machine with regular
> internet access, this should just work; if it doesn't, that's worth
> reporting.

---

## Path B: Manual Setup (for active development)

Four pieces run as separate processes: Postgres, Redis, the API, and
(optionally, for document uploads to actually process) the background
worker. The frontend is a fifth, separate process.

### 1. Postgres + pgvector

```bash
# Install Postgres 16 and the pgvector extension for your platform, e.g.
# on Debian/Ubuntu:
sudo apt-get install postgresql-16 postgresql-16-pgvector

# Start it, then create the database:
sudo -u postgres psql -c "CREATE DATABASE enterprise_ai_platform;"
```

The `vector` extension itself is enabled by this project's own first
migration (`1e6a7533ea17_enable_pgvector_extension.py`) when you run
`alembic upgrade head` below — you don't need to `CREATE EXTENSION`
yourself.

### 2. Redis

```bash
sudo apt-get install redis-server
sudo service redis-server start
```

### 3. Backend environment

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` includes `sentence-transformers` (and its `torch`
dependency), which is a large download (several GB) — this is the real
embedding model used for search (see `docs/adr/ADR-008-embedding-provider.md`).
If you're on a constrained machine and only want to work on parts of the
app that don't need real embeddings, you can install everything except it:

```bash
grep -v sentence-transformers requirements.txt | pip install -r /dev/stdin
```

(Search/RAG/document-processing tests will fail without it — this is a
genuine trade-off, not a fully-functional substitute.)

Also install the OCR/file-type system dependencies used by document
ingestion:

```bash
sudo apt-get install tesseract-ocr libmagic1
```

Copy and configure the environment file:

```bash
cp ../.env.example .env
```

Edit `backend/.env` — the defaults point at `localhost` for Postgres and
Redis, which is correct for this manual setup path (unlike the Docker
Compose path, where those get overridden to point at service names — see
`docs/adr/ADR-019-docker-compose.md`). At minimum, set a real `JWT_SECRET`.

### 4. Run migrations

```bash
# still inside backend/, with the venv active
alembic upgrade head
```

### 5. Choosing an LLM provider

Set in `backend/.env`:

```bash
# Option A: Ollama (local, free, no API key)
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
# Then separately: install Ollama, run `ollama pull llama3.1:8b`

# Option B: Anthropic (real API calls, needs a key)
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=<your key>
```

See `docs/adr/ADR-004-llm-provider-abstraction.md` and
`docs/adr/ADR-010-llm-provider-and-rag-prompting.md`
for why the app is built to support either interchangeably.

### 6. Frontend environment

```bash
cd ../frontend
npm install
```

The frontend talks to the backend via `NEXT_PUBLIC_API_BASE_URL`, which
defaults to `http://localhost:8000` if unset — correct for this manual
setup with the backend on its default port. No `.env` file is required
for local dev unless you're running the backend on a different port.

---

## Verifying your setup

Whichever path you used:

1. **Health check**: `curl http://localhost:8000/api/v1/health` should
   return `{"status":"ok",...}`.
2. **Register an account**: open http://localhost:3000/register and
   create one — this also creates your first organization, with you as
   its admin.
3. **Upload a document**: from the Documents page, upload a `.txt` or
   `.pdf` file. Its status should move from `pending` → `processing` →
   `completed` within a few seconds (this needs the worker process
   running — see [`EXECUTION_GUIDE.md`](EXECUTION_GUIDE.md) if it stays
   `pending`).
4. **Ask a question**: from the Chat page, ask something about the
   document you uploaded. This needs a real, reachable LLM provider (step
   5 above) — if it fails, check that Ollama is running and has the model
   pulled, or that your Anthropic key is valid.

If all four work, your setup is complete.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `connection refused` on port 5432/6379 | Postgres or Redis isn't running — start it (Path B) or check `docker compose ps` (Path A) |
| Documents stuck on `pending` forever | The worker process isn't running (Path B) or the `worker` container isn't healthy (Path A: `docker compose logs worker`) |
| Chat/agent requests fail | No LLM provider is reachable — check `LLM_PROVIDER`, and that Ollama/Anthropic is actually configured and reachable |
| App refuses to start, mentions `JWT_SECRET` | You're running with `ENVIRONMENT=production` and the default secret — either set `ENVIRONMENT=development` for local work, or generate a real secret (`openssl rand -hex 32`) |
| Frontend shows network errors on every page | `NEXT_PUBLIC_API_BASE_URL` is misconfigured, or doesn't match where the backend is actually listening — see `docs/adr/ADR-019-docker-compose.md` decision 3 for the exact build-time-vs-runtime gotcha this variable has |
