# CLAUDE.md — Enterprise AI Knowledge & Workflow Platform

This file is the standing reference for how this codebase is built and maintained.
Read this before making architectural changes.

## 1. What this project is

A multi-tenant enterprise platform that ingests organizational documents, indexes them
with hybrid (semantic + keyword) search, answers questions with cited RAG, and runs a
constrained agent system with human-approved tool use. Not a chatbot demo — production
patterns throughout: auth, RBAC, tenant isolation, observability, evaluation, tests.

## 2. Technology stack (locked decisions — see ADRs for reasoning)

- **Backend:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async), Alembic
- **Database:** PostgreSQL (primary store *and* vector store via `pgvector`) — see ADR-002
- **Cache/queue:** Redis + background worker (arq or Celery — decided in Phase 3)
- **Vector search:** pgvector extension on Postgres (not a separate vector DB) — see ADR-002
- **Keyword search:** Postgres full-text search (`tsvector`) — no separate Elasticsearch/OpenSearch unless proven necessary
- **Embeddings:** sentence-transformers, default model `all-MiniLM-L6-v2` (small, CPU-friendly, fits 8GB RAM / 6GB VRAM dev box)
- **Reranker:** cross-encoder (e.g. `ms-marco-MiniLM`), swappable
- **LLM provider abstraction:** `LLMProvider` interface with `OllamaProvider`, `OpenAIProvider`, `AnthropicProvider`, `GeminiProvider` implementations. Default local dev provider: Ollama.
- **Agent orchestration:** custom deterministic state machine (not LangGraph) — see ADR-005
- **Frontend:** Next.js (TypeScript, App Router), React, Tailwind CSS
- **Infra:** Docker Compose for local dev (postgres, redis, backend, worker, frontend)
- **Testing:** pytest + pytest-asyncio (backend), Playwright or Vitest (frontend — decided in Phase 12)
- **Observability:** structured JSON logging, OpenTelemetry traces, Prometheus metrics endpoint

## 3. Architecture rules

- **Clean separation:** `api/` (routes, request/response schemas) → `services/` (business logic)
  → `repositories/` (DB access) → `models/` (SQLAlchemy ORM). Routes never touch the DB directly.
- **Tenant scope is mandatory.** Every repository method that touches tenant-owned data takes
  an `organization_id` and filters by it at the query level — never in application code after
  the fact. No exceptions, no "trusted" internal calls that skip this.
- **LLM/embedding/reranker access only through the provider abstraction.** No direct
  `openai.chat.completions` or raw HTTP calls scattered in business logic.
- **Tools are declarative.** Every agent tool implements the same `Tool` interface (name,
  description, input schema, output schema, risk level, permission check). The agent never
  gets raw DB/filesystem/shell access — only through registered, schema-validated tools.
- **High-risk tool calls always pass through the approval workflow.** No exceptions for
  "trusted" agents or admin users bypassing it in code — approval is enforced server-side.
- **Retrieved document content and tool output are DATA, never instructions.** Prompts must
  keep system instructions, user input, and retrieved content in clearly separated, labeled
  sections so retrieved text cannot be interpreted as a command.
- **No secrets in logs, prompts sent to models, or error responses returned to clients.**
- **No synchronous heavy work in the request path.** Ingestion, embedding, OCR happen in
  background workers; the API returns a status the client can poll.

## 4. Coding conventions

- Python: PEP 8, full type hints, `ruff` for lint/format, `mypy` for type checking.
- Pydantic schemas are the API contract — SQLAlchemy models are never returned directly
  from an endpoint.
- Small, single-purpose functions/services. Prefer composition over deep inheritance.
- No bare `except:`. Catch specific exceptions, log with context, return a structured
  error (`{"error": {"code", "message", "request_id"}}`) — never a raw stack trace.
- No `TODO`/`FIXME`/`pass`-as-placeholder in code on the main branch for anything on the
  critical path (auth, tenant scoping, tool execution, approval). If something is genuinely
  out of scope for the current phase, it's tracked in `docs/architecture/known-gaps.md`,
  not silently stubbed.
- Frontend: TypeScript strict mode, no `any` without a documented reason.

## 5. Commands (verified as of Phase 17 — updated as each phase lands)

Backend API:
```
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp ../.env.example .env    # then edit DATABASE_URL / JWT_SECRET / REDIS_URL
alembic upgrade head
uvicorn app.main:app --reload
```

Background worker (required for document ingestion — run as a separate
process alongside the API, not inside it):
```
cd backend && source .venv/bin/activate
arq app.workers.settings.WorkerSettings
```

Frontend (Phase 12 — real UI, not a scaffold):
```
cd frontend
npm install
npm run dev                # requires the backend API running on :8000
                            # (override via NEXT_PUBLIC_API_BASE_URL)
npm run typecheck && npm run lint && npm run build
```
`lib/api/schema.d.ts` is generated from the backend's live OpenAPI schema,
not hand-typed — regenerate after any backend schema change:
```
curl -s http://localhost:8000/openapi.json > frontend/openapi.json
cd frontend && npx openapi-typescript openapi.json -o lib/api/schema.d.ts
```

Docker Compose (Phase 16 — the whole stack, five services, one command on
a machine with normal registry access; see ADR-019 for exactly what was
and wasn't verified in this sandbox):
```
cp .env.example .env       # at minimum, set a real JWT_SECRET
docker compose up --build
```

Dependency vulnerability scans (Phase 17 — run periodically, not just once):
```
cd backend && pip install pip-audit && pip-audit -r requirements.txt
cd frontend && npm audit
```

Backup / restore (Phase 17 — requires the Docker Compose stack running):
```
./scripts/backup.sh
./scripts/restore.sh path/to/backup.sql.gz
```

Tests / quality gates:
```
pytest                     # requires a running Postgres AND Redis — see below
ruff check . && ruff format --check .
mypy app evaluation
```

Evaluation suite (spec §27/§28 — real code, not a stub):
```
cd backend && source .venv/bin/activate
python -m evaluation.run              # retrieval + citation metrics only
python -m evaluation.run --llm-judge  # also runs LLM-as-judge faithfulness/relevance
```
Ingests a small golden dataset through the real pipeline, runs real hybrid
search + RAG generation against it, computes retrieval (recall/precision/
MRR/NDCG) and citation-correctness metrics, persists the run, and compares
against the previous run for the same dataset version — flags regressions
and exits non-zero if any are found. Requires whatever `LLM_PROVIDER`/
embedding provider is configured in `.env` to actually be reachable; in this
sandbox that fails at the embedding step (same constraint as everywhere
else — see ADR-008) but the harness itself runs to completion and reports
the failure accurately per-case rather than crashing.

Backend tests require real PostgreSQL and Redis instances (not SQLite/fakes —
see ADR-001, ADR-007). `tests/conftest.py` points at a dedicated test database
(`enterprise_ai_platform_test`) and a dedicated Redis logical DB (index 15)
regardless of what `.env` says, and uses a fresh temp directory for file
storage per test run — so running the test suite never touches dev data.
Locally (no Docker yet — that's Phase 15), the simplest setup:
```
sudo apt-get install postgresql redis-server postgresql-16-pgvector
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'postgres';"
sudo -u postgres createdb enterprise_ai_platform
sudo -u postgres createdb enterprise_ai_platform_test
sudo service postgresql start && sudo service redis-server start
cd backend && alembic upgrade head
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/enterprise_ai_platform_test alembic upgrade head
```

> **`sentence-transformers` is a real dependency in `requirements.txt` but is
> NOT installed in this sandbox's working venv** — its PyTorch dependency
> exhausted this sandbox's disk budget, and separately, the model weights
> download from `huggingface.co`, which this sandbox's egress proxy blocks
> outright. Neither applies to your actual machine. Tests exercise the
> chunking → embedding → pgvector pipeline via a small deterministic fake
> provider (`tests/fakes.py::FakeEmbeddingProvider`, injected via DI) and
> verify the real provider's own wrapper logic by mocking the import
> boundary (`tests/test_sentence_transformers_provider.py`) — see ADR-008.
> To actually run embeddings for real, install the full `requirements.txt`
> on a machine with normal internet access.

Frontend (once Phase 12 scaffolding exists):
```
cd frontend
npm install
npm run dev
npm test
```

Full local stack:
```
docker compose up
```

> This section will be corrected as soon as it drifts from reality — commands are verified
> by actually running them, not assumed.

## 6. Environment requirements

- Local dev target: 8GB RAM / RTX 3050 6GB VRAM / Windows — local LLM inference must stay
  within this budget (small quantized models via Ollama), never assume a large local model.
- Sandbox used for iterative development in this conversation: no Docker, no GPU, 1 vCPU,
  ~3.9GB RAM. Full containerized-stack verification and GPU-path testing happen on the
  target machine, not in the sandbox — this is tracked explicitly per phase, not glossed over.

## 7. Security rules (non-negotiable, see docs/architecture/security.md for detail)

- No plaintext passwords; bcrypt/argon2 hashing only.
- `DEBUG` must default to `false` everywhere (app settings, `.env.example`, test
  fixtures). Starlette's debug mode returns raw tracebacks for unhandled exceptions
  and checks this *before* any custom exception handler — a `debug=True` default
  already caused a real stack-trace leak once (Phase 6, found via live smoke testing,
  fixed and regression-tested in `test_error_handling.py`). Never set it true except
  for a short, deliberate local debugging session.
- No unrestricted SQL execution from the agent — only a schema-validated, read-only,
  keyword-denylisted safe-SQL path (`DROP/DELETE/UPDATE/INSERT/ALTER/TRUNCATE` rejected
  by default).
- No shell execution reachable from the LLM under any circumstance.
- Tenant isolation is tested explicitly (cross-tenant access attempts must return 403/404,
  never leak existence of another tenant's resource).
- File uploads: size limits, extension allowlist, MIME sniffing, filename sanitization,
  storage path isolation per tenant.

## 8. Development workflow

Each phase follows: explain → list files touched → implement → test → lint/typecheck →
run app-level checks → fix → re-verify → update docs. A phase is not "done" until its
tests actually pass, not until the code merely looks correct.

## 9. Key design decisions log

See `docs/adr/` for full ADRs. Summary:
- ADR-001: PostgreSQL as sole primary datastore (not split across multiple DB engines)
- ADR-002: pgvector over a standalone vector DB (Qdrant) for this scale — one fewer
  service to run/secure/back up; revisit if vector volume/query load outgrows it
- ADR-004: Provider abstraction for LLM/embeddings/reranker, default local = Ollama
- ADR-005: Custom deterministic agent state machine over LangGraph, to keep step limits,
  approval gating, and state inspection fully explicit and testable
- ADR-006: Multi-tenancy via shared schema + `organization_id` column + enforced repository-
  level filtering (not schema-per-tenant) — simpler ops, sufficient isolation when enforced
  correctly and tested for it
- Password hashing: argon2id via `argon2-cffi` directly (not passlib — its bcrypt
  version-detection has a known break with bcrypt>4.1; argon2id is also OWASP's
  current first recommendation over bcrypt)
- Access tokens: short-lived JWT (HS256, `jti` + `iat`/`exp`/`type` claims). Refresh
  tokens: opaque random value, only its SHA-256 hash stored, rotated on every use —
  a JWT can't be individually revoked without a blocklist, which defeats the point
  of using one for something that must be revocable (logout, detected reuse)
- Cross-tenant access returns 404 (not 403) so a user outside an organization can't
  distinguish "doesn't exist" from "you're not in it" (spec §36); once membership is
  confirmed, insufficient role is 403 — that distinction is safe to reveal at that point
- ADR-007: `arq` for the background job queue over Celery — async-native, fits the
  all-async stack directly, avoids operational weight this scale doesn't need
- File storage: local filesystem behind a `FileStorage` protocol (tenant-isolated by
  directory, generated filenames never derived from user input), swappable for an
  S3-compatible implementation later without touching calling code
- File validation is two-layered: extension allowlist AND real content sniffing via
  libmagic, cross-checked against each other — an extension alone is never trusted,
  which is what actually stops a renamed/spoofed file from being accepted
- Text extraction (TXT/MD/CSV/PDF/DOCX/XLSX/PPTX + OCR for standalone images via
  Tesseract) is genuinely implemented per format, not stubbed — this phase's ingestion
  pipeline stops at "extracted_text is available on the Document row"; chunking and
  embedding are Phase 5/6, not folded in here
- OCR for *scanned/image-only PDFs* is explicitly NOT implemented yet (would need
  poppler + a page-rasterization step) — a scanned PDF fails extraction with a clear
  reason rather than silently returning empty text; tracked as a known gap, not hidden
- ADR-008: `sentence-transformers` (`all-MiniLM-L6-v2`, 384-dim) confirmed as the
  default embedding provider — behind the same `EmbeddingProvider` DI seam pattern as
  storage/LLM. Its heavy dependency and Hugging Face download can't run in this sandbox
  (blocked network + disk budget), so the provider's own import is deliberately lazy,
  letting its wrapper logic be unit-tested via mocking while a small deterministic
  `FakeEmbeddingProvider` (tests-only, real word-hashing algorithm) exercises the actual
  chunking → embedding → pgvector storage → similarity-search pipeline against real
  Postgres
- Chunking is character-based, not token-based — a real tokenizer (tiktoken) also needs
  a download from a blocked host, and char-based chunking with paragraph/sentence-aware
  splitting is a legitimate, common approach at this scale (not a compromise unique to
  this environment)
- pgvector's HNSW index (cosine ops) is created explicitly in the migration — Alembic's
  autogenerate doesn't know to create vector indexes, and separately failed to import
  the `pgvector` module it referenced in the generated type name; both required manual
  correction of the autogenerated migration, not just accepting its output as-is
- Document.status COMPLETED now means "chunked, embedded, and retrievable," not just
  "text extracted" (which was Phase 4's narrower, intentionally provisional meaning) —
  this matches the spec's actual 4-state status model rather than inventing a 5th state
- ADR-009: reranking follows the identical ADR-008 pattern (real `CrossEncoderReranker`,
  lazy import, mocked unit tests, fake-but-real-algorithm pipeline tests) since it hits
  the exact same Hugging Face/disk sandbox constraint — reused rather than re-litigated
- Hybrid search fuses semantic (pgvector cosine) and lexical (Postgres `ts_rank`) scores
  via min-max normalization within the candidate pool, then a configurable alpha/beta
  weighted sum — the two raw scores are on incomparable scales and can't be combined
  directly
- **Real bug found via live smoke testing, not code review**: `Settings.debug` defaulted
  to `True`, which makes Starlette's `ServerErrorMiddleware` return raw Python
  tracebacks for unhandled exceptions — checked *before* any registered custom
  exception handler, completely bypassing the safe JSON error handler built in Phase 2.
  A live curl request against the real running server exposed full file paths and stack
  frames in the HTTP response. Fixed by defaulting `debug=False`; a stale `.env` file
  and the shared test fixture both had to be corrected too, since either could have
  masked this exact bug in test coverage. Locked in with a regression test
  (`test_error_handling.py`) verified to actually fail without the fix, not just pass
  incidentally.
- ADR-010: `AnthropicProvider` (real SDK, lightweight — no PyTorch, unlike ADR-008/009's
  dependencies) and `OllamaProvider` (plain httpx) both implemented as real code. Unlike
  the embedding/reranking models, `api.anthropic.com` is genuinely reachable from this
  sandbox — confirmed live twice: a raw curl got a real `401 authentication_error`, and
  separately `AnthropicProvider` itself (our actual code, not a mock) made a real call
  and correctly surfaced the SDK's typed `AuthenticationError`. The only missing piece
  is an API key, not network/host access — a materially different constraint than
  ADR-008/009's, documented as such rather than conflated with it.
- RAG prompt construction keeps system instructions, retrieved documents, and the user
  question in three distinct, explicitly labeled sections (never concatenated) — the
  system prompt explicitly instructs the model to treat `<retrieved_documents>` content
  as data, never as instructions to follow, regardless of what it claims to be (spec
  §38). Structurally verified (labeling, separation, position) since genuine behavioral
  injection-resistance needs a real model call this sandbox can't make.
- Citations are validated, never trusted: `[n]` markers are extracted from the model's
  answer and cross-checked against the actual retrieved chunk set — an out-of-range
  number is silently dropped, never persisted. Proven end-to-end (not just unit-tested)
  by deliberately forcing a fake LLM to hallucinate `[99]` through the real HTTP API and
  confirming zero citations were created.
- Zero retrieved chunks short-circuits to a fixed "no relevant information" response
  without an LLM call — cheaper, and removes any risk of an ungrounded general-knowledge
  answer for a query the org's own documents don't cover.
- ADR-011: evaluation covers RAG retrieval/generation/system metrics only — agent
  evaluation metrics are explicitly deferred to Phase 9, since there's no agent system
  yet to measure. Retrieval metrics (recall/precision/MRR/NDCG) and citation correctness
  are pure/deterministic, no LLM needed; faithfulness/relevance use an LLM-judge
  following the exact ADR-008/009/010 pattern (real implementation, mocked unit tests,
  fake-provider pipeline tests, documented sandbox limitation) since they're inherently
  semantic judgments a formula can't make
- A live run of `python -m evaluation.run` against real infrastructure failed at the
  embedding step (expected, same constraint as every phase since 5) but this itself
  validated the harness's resilience design: golden-document ingestion succeeded, each
  case's failure was caught individually rather than crashing the whole run, and the run
  was correctly marked COMPLETED (the evaluator itself worked) with error_rate=1.0
  (the thing being evaluated didn't) — a deliberate distinction, not a bug
- Regression detection is relative-only: two consecutive live runs with a 100%-broken
  embedding provider both correctly showed "no regressions" since error_rate stayed flat
  at its worst value rather than getting worse. Found during independent re-verification,
  not by design intent — tracked as a known gap in PLAN.md (an absolute sanity threshold
  would complement the relative check for a real CI gate), not fixed in this phase.
- ADR-012: the agent planner uses ReAct-style JSON prompting, not native provider
  tool-calling — keeps the Ollama default (ADR-004) uniform with Anthropic rather than
  needing two different code paths, and needs zero changes to the Phase 7 LLMProvider
  protocol. Execution is synchronous within the request up to MAX_STEPS/MAX_RUNTIME,
  pausing (not blocking) at HIGH_RISK tool selection for a real, separate approval
  endpoint to resume — a known trade-off (no cross-process resumability) documented
  rather than hidden.
- Safe SQL tool (run_safe_sql) stacks four independent, genuinely real defense layers:
  statement-shape validation, keyword blocklist, table allowlist (a dedicated migration
  view excluding extracted_text and any auth table), and a database-enforced
  `SET TRANSACTION READ ONLY` on a separate connection — proven live that layer 4 is the
  one that actually matters if the others have a gap.
- **Three real bugs found via testing this phase, all the same root cause**: repository
  methods constructed child ORM objects (AgentStep, ToolCall, Approval) via raw foreign-key
  columns instead of SQLAlchemy relationship attributes, bypassing the ORM's in-memory
  sync entirely. The deepest instance wasn't just a serialization bug — `run.steps`/
  `run.tool_calls` stayed stale *throughout the agent loop's own execution*, meaning the
  transcript-reconstruction function would never see earlier steps in the same run
  (planner amnesia) and MAX_TOOL_CALLS counting would never actually trigger. Fixed by
  taking the `run`/`tool_call` object directly and syncing in-memory collections/
  relationships alongside every DB write, not just relying on a later re-fetch.
- A fourth bug was in test code, not app code: a dependency-override lambda that rebuilt
  `SequencedLLMProvider` on every call silently reset its call-sequence state across the
  two separate HTTP requests the approval flow spans — found because the test failed with
  a *plausible-looking* wrong result (stuck at `awaiting_approval`) rather than a crash,
  a reminder that a passing-looking wrong answer needs the same scrutiny as an outright
  failure.
- Live-verified: a real agent run against unreachable infrastructure (no Ollama server)
  was caught by the agent's *own* failure handling (spec §21), not just the generic
  app-level safety net — the run correctly completed its lifecycle with `status: failed`
  and a clear, safe `error_message`, returning a normal 201, not a crash or a 500.
- ADR-013: Phase 10 audited the Phase 9 tool system against spec §22/§23 rather than
  rebuilding it, and found two real gaps (not just documentation gaps): every tool had
  unrestricted access to the full `Settings` object — including the JWT secret, every LLM
  API key, and DB/Redis URLs with embedded credentials — even though zero tools used it.
  Since tool output is echoed into the LLM conversation transcript and persisted, this was
  a real leak surface, not theoretical; removed `Settings` from `ToolExecutionContext`
  entirely (least privilege at the type level, not just current non-use). Also added the
  `output_schema` spec §22 explicitly requires but Phase 9 never declared — `Tool.run()`
  now validates successful output against it, proven to actually reject a mismatch via a
  deliberately misbehaving test-only tool, not just accept correct output.
- Added `draft_email` (closes a named spec §22 example gap with real substance: composes
  text only, never sends, since no SMTP integration exists) but deliberately did NOT add
  `create_ticket` — no ticketing domain exists anywhere in this app, and inventing one
  purely to match an example tool's name would be exactly the hollow, substance-free
  feature the project's "no fake implementations" principle rules out.
- Added `GET /api/v1/tools` (tool discovery/introspection) using `CurrentUser`, not
  `CurrentMembership` — caught my own mistake here (first draft required an
  `organization_id` for metadata that's identical across every org) via a real
  422-then-fix, not assumed correct.
- Agent evaluation metrics (spec §27's second list, deferred from Phase 9) added as pure
  functions in `evaluation/agent_metrics.py`, same verification pattern as
  `retrieval_metrics.py` (hand-worked values) plus a real integration test proving the
  metrics correctly *penalize* a genuinely poorly-behaved real agent run (off-task tool
  use, unnecessary calls) — not just that they report good scores on a happy path. Three
  of spec's six listed agent metrics implemented (task success rate, tool selection
  accuracy, unnecessary tool calls); tool argument correctness, failure recovery, and a
  completion-rate metric distinct from success rate are explicitly scoped out, tracked in
  PLAN.md, not silently dropped.
- ADR-014 (observability): request-scoped correlation (request_id/user_id/organization_id)
  via `contextvars` + a logging filter, so any `logger.info(...)` anywhere during a
  request carries full correlation context automatically, not just calls that remember to
  pass `extra={...}`.
- **Real bug found via live empirical testing, not assumed correct**: the first
  implementation used `@app.middleware("http")` (Starlette's `BaseHTTPMiddleware`). Live-
  tested against a real authenticated request and found `user_id` completely missing from
  the request-completed log line, despite auth having definitely succeeded — a real,
  well-documented `BaseHTTPMiddleware` limitation (it runs the downstream app in a
  separate task, so contextvars set deep in request handling never propagate back out to
  code after `call_next()`). Rewrote as a pure ASGI middleware
  (`app/observability_middleware.py`), which runs everything in one task, and
  re-verified live that this actually fixes it.
- Prometheus metrics (`GET /metrics`, root-level, unauthenticated per standard practice)
  implement spec's exact named list. Route-template labels (e.g.
  `/api/v1/documents/{document_id}`), never resolved paths with real IDs substituted in —
  the latter would create one label series per unique ID ever requested, a well-known
  Prometheus high-cardinality trap.
- "Tracing where practical" (spec §29) means request-ID correlation across the API/worker
  process boundary, not full OpenTelemetry — reasoned, not just convenient: this is a
  modular monolith plus one background worker, not a microservices topology where
  distributed tracing's cross-service-correlation value actually pays for its complexity.
  Live-verified end-to-end: uploaded a document with a client-supplied `X-Request-ID`,
  confirmed the SAME ID appears in the API's request-completed log, arq's own
  job-execution log, AND the worker's own structured error log for that job (which hit
  the expected, same-as-every-phase-since-5 missing-`sentence_transformers` failure) —
  correlation held even through a real failure, which is when it matters most.
- Found and fixed a real Phase 8 gap while building this phase — corrected here after
  initially misdescribing it: ADR-011 anticipated cost tracking, but the evaluation
  runner's per-case `metrics` dict (a flexible JSONB bag by design, not individual
  columns — see Phase 8's actual accepted model, which has no `estimated_cost_usd` field
  at all) never included token usage or cost keys, because `RagAnswer` didn't expose the
  underlying LLM call's token counts to its caller in the first place — they were a local
  variable trapped inside `RagService.ask()`. Fixed properly, not worked around: added
  `model`/`input_tokens`/`output_tokens` fields to `RagAnswer` itself (populated from the
  real `LLMResponse`, `None` specifically on the zero-search-results path where no LLM
  call happens), then wired the evaluation runner to record real per-case token usage and
  `estimated_cost_usd` via the same `app/core/pricing.py` built for the MODEL_COST metric.
  Verified with a real test proving the values actually flow through end-to-end, not just
  that the fields exist.
- Caught a second real gap the same careful way, this time flagged by my own PLAN.md note
  going into the phase: the agent system had zero `logger` calls anywhere, despite spec
  §29 explicitly listing "tool calls" as a required structured-log field — only the
  AGENT_STEPS metric (a count) existed, no actual log lines. Added real logging at every
  meaningful transition in `AgentRepository` (step recorded, tool selected, executed/
  failed/rejected, awaiting approval, human decision made), verified with a real
  integration test that scripts a full agent run — including a genuine HIGH_RISK approval
  flow — through the real HTTP API and asserts on the actual captured log records. The
  test's own captured output was itself a nice confirmation: agent log lines automatically
  carry the same request_id/user_id/organization_id correlation as HTTP logs, for free,
  via the same context filter, since agent runs execute synchronously within the request.
- ADR-015 (Phase 12, frontend): real UI finally built on top of 11 backend-only phases.
  Types generated from the backend's actual live `/openapi.json` (`openapi-typescript`),
  not hand-guessed — spot-checked against the real schema before use.
- **Real, permanent sandbox constraint found and properly solved, not worked around**:
  `next build` failed because `fonts.googleapis.com` isn't in this sandbox's network
  allowlist (same category as `huggingface.co` being blocked for `sentence-transformers`
  on the backend). Rather than abandon the type choices or ship an unverified build,
  switched from `next/font/google` to self-hosted `@fontsource/*` packages (installable
  via the allowed npm registry) — genuinely better practice regardless of the constraint
  (no runtime third-party font-CDN dependency), verified with a real, clean production
  build afterward, not just assumed to work.
- Same permanent-constraint pattern hit again attempting real browser-based E2E testing:
  Playwright's Chromium download comes from `cdn.playwright.dev`, also not allowlisted.
  Rather than claim untested UI code was verified, fell back to the strongest achievable
  verification in this sandbox: a real production build, a real running server, real HTTP
  requests against the real live backend replicating the frontend's exact API-client and
  citation-parsing logic (including the hallucinated-citation edge case — confirmed an
  out-of-range `[99]` marker correctly renders as literal text, not a broken chip,
  preserving the backend's own citation-validation guarantee end-to-end). What remains
  unverified — actual visual rendering, click interactions, layout — needs a real browser
  on your machine, stated plainly rather than glossed over.
- Scope: Phase 12 covers the core RAG loop (auth, documents, chat with citations) end to
  end. Agent-run UI with human approval and admin/evaluation dashboards are deliberately
  deferred — flagged as real next-phase candidates in PLAN.md, not silently dropped.
- ADR-016 (Phase 13, agent UI): since `POST /agents`/`.../approve`/`.../reject` are all
  synchronous backend calls that can take up to `MAX_RUNTIME_SECONDS` (90s), the loading
  state names what's actually happening rather than showing a bare spinner that reads as
  broken. The approval panel deliberately inverts the usual button-emphasis convention —
  Approve uses the danger style, Reject the calmer secondary style — since for an
  irreversible high-risk action, calm should be the default posture.
- **Real bug found via live verification against the actual backend, not assumed
  correct**: `useStartAgentRun` was typed against `AgentRunResponse`, but a live check
  against the real running server showed `POST /api/v1/agents` actually returns
  `AgentRunDetailResponse` (confirmed by checking the route's literal `response_model=`
  declaration) — the live response included `steps`/`tool_calls` fields my type didn't
  know about. Fixed to the correct type, which also enabled a genuine improvement (pre-
  populating the detail-page query cache from the start-run response, so navigating to
  the new run doesn't need a redundant fetch).
- Same honest verification pattern as Phase 12 for the parts a browser is needed for:
  the approval-detection logic (finding the one tool call actually awaiting a pending
  decision) was verified against realistic schema-accurate data, including two negative
  cases that matter — an already-decided approval must not re-trigger the panel, and a
  run with no tool calls must not show it at all.
- `AgentStepResponse` has no `tool_call_id` and `ToolCallResponse` has no timestamp — the
  API genuinely can't correlate a specific reasoning step to a specific tool call, or
  interleave them chronologically. Rather than fabricate a merged timeline the data
  doesn't support, steps and tool calls render as two honest, separate sections — a real,
  stated API limitation (ADR-016 decision 2), not a UI shortcut.
- ADR-017 (Phase 14, rate limiting, spec §39): fixed-window Redis counters, applied via a
  per-route dependency factory (matching the existing `require_roles()` pattern) rather
  than a blanket middleware, since different endpoints have genuinely different real
  costs. A separate, tighter failed-login throttle — keyed by email, not IP — protects one
  targeted account against credential stuffing spread across many source IPs, which the
  general per-IP route limit on `/auth/login` can't do on its own.
- **A real, significant pre-existing gap found and fixed, not routed around**: writing a
  test that finally asserted on a 429 response's JSON *body* (not just its status code)
  revealed that `handle_http_exception` (Phase 2/6/11) had claimed since its own comment
  to "ensure the response shape is consistent everywhere," but actually delegated to
  FastAPI's default handler — producing `{"detail": ...}` for every plain `HTTPException`,
  not the `{"error": {code, message, request_id}}` shape every other error path used.
  Fixed properly, verified safe app-wide (zero existing tests depended on the old shape;
  full 279-test suite still passes).
- That fix mattered well beyond rate limiting: tracing through the frontend's `ApiError`
  constructor (Phase 12) showed it reads `body.error.message` unconditionally — against
  the old `{"detail": ...}` shape, that access would throw inside the constructor itself,
  meaning every 401 (wrong password), 403, 404, and 409 response since Phase 12 was
  silently falling back to a generic frontend error message instead of the real one, on
  login, register, documents, and agent pages alike. This session's backend fix
  retroactively resolves that cross-phase bug — found by tracing the chain, not assumed.
- A third self-caught bug: the failed-login throttle's metric/log emission was originally
  inside a code path that's actually unreachable once an account is already locked out
  (the read-only pre-check intercepts every subsequent attempt before `record_failed_login`
  could ever run again). Found via live testing against a real running server with
  production-default limits — the metric simply never incremented for 17 of 22 real
  blocked requests — and fixed by moving the emission to the actual enforcement point.
- ADR-018 (Phase 15, admin/evaluation dashboards): checked `EvaluationRun.organization_id`
  directly before designing anything and confirmed it points at Phase 8's throwaway
  system org, not any real customer org — so the dashboard's evaluation endpoints are
  deliberately platform-wide, not scoped the way every other endpoint in this app is.
  Verified live: an admin of a completely different, freshly-registered org could see an
  evaluation run belonging to the throwaway eval org, exactly as designed.
- Admin access reuses "ADMIN role in at least one organization" rather than building a
  genuine platform-admin role system — a stated scope decision (this app has no such
  separate concept), not silently assumed. Frontend nav gating checks the exact same
  condition (`user.memberships.some(m => m.role === "admin")`) as the backend's
  `require_platform_admin` dependency, verified live via the same E2E script pattern used
  since Phase 12, so the UI never offers a link a request would then reject.
- The metrics dashboard is explicitly labeled a live snapshot, not a historical chart —
  Prometheus counters are in-process and cumulative-since-startup only, with no real
  time-series storage this project runs. Built by reading the exact same live registry
  `/metrics` already exposes (`prometheus_client`'s own `.collect()` API), not a second,
  parallel counting mechanism that could drift from what `/metrics` reports.
- ADR-019 (Phase 16, Docker Compose): a genuinely new kind of sandbox finding — installed
  `docker.io`/`docker-compose-v2` via `apt` (not present by default, unlike every other
  tool used throughout this project) and discovered the daemon itself actually runs here
  (`docker ps` responds normally), but `registry-1.docker.io` returns a real, confirmed
  `403 Forbidden` — the daemon works, the registry doesn't, a more specific variant of the
  same permanent network-allowlist constraint as `huggingface.co`/`fonts.googleapis.com`/
  `cdn.playwright.dev`. Even `docker build --check` (BuildKit's Dockerfile linter) needs to
  resolve its own syntax directive from Docker Hub first, so it's equally blocked —
  confirmed directly, not assumed, and documented rather than silently dropped.
- What *was* genuinely verified, not just written and hoped correct: `docker compose
  config` fully parsed and validated the whole compose file without needing any registry
  access — resolved `DATABASE_URL`/`REDIS_URL` correctly pointing at service hostnames
  (not `localhost`), confirmed the `worker` service's `command` override and its
  `condition: service_healthy` dependency on `api` (not just `service_started`), confirmed
  the build-arg wiring, confirmed the shared upload volume. Real tool execution, the same
  standard as `tsc`/`ruff`/`mypy` elsewhere in this project — not a rubber-stamp check.
- **A real, previously undiscovered bug found and fixed**: `.env.example` instructed users
  to set `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1`, but every frontend hook
  call already includes `/api/v1/...` in its own path argument (`lib/api/client.ts`) —
  following that literal instruction would have produced duplicated
  `/api/v1/api/v1/...` URLs and silent 404s. Never caught in five prior phases of live
  testing because this variable was never actually set explicitly before, always falling
  back to the code's own correct default — only surfaced now because Docker Compose
  genuinely required setting it via a build arg for the first time.
- A genuinely correct `NEXT_PUBLIC_*` build-time-vs-runtime distinction: these variables
  are inlined into the client JavaScript bundle at `next build` time, not read from the
  container's environment at runtime — setting one only under `docker-compose.yml`'s
  `environment:` key would silently do nothing, since by container start the value is
  already baked into static files built without it. `frontend/Dockerfile` takes it as a
  build `ARG`; `docker-compose.yml` passes it via `build.args`, not `environment`.
- ADR-020 (Phase 17, production-readiness audit): a real `pip-audit` run against the live
  vulnerability database found genuine CVEs in `fastapi`/`starlette`/`pyjwt`/
  `python-multipart`/`pypdf`/`pillow`; `npm audit` found real findings in `eslint`/
  `postcss`. Every upgrade was empirically tested in an isolated venv against the real
  292-test suite, `ruff`, and `mypy` before being adopted — including confirming directly
  that a patched `starlette` is genuinely incompatible with the old pinned `fastapi`
  (`fastapi 0.115.6 requires starlette<0.42.0,>=0.40.0`, pip's own resolver said so) before
  jumping FastAPI itself twenty-six minor versions ahead. Result: zero known vulnerabilities
  across the whole dependency set, confirmed by re-running the scanners after the fix, not
  assumed from the version bump alone.
- The upgrade itself surfaced two real, previously-unnoticed issues, both fixed: a
  deprecated FastAPI status constant (verified the replacement resolves to the same 422
  value before renaming, not assumed) and a test using an 11-byte JWT secret short enough
  to trigger PyJWT's new `InsecureKeyLengthWarning`.
- A real, meaningful safety net, not just documentation: the app now refuses to start if
  `ENVIRONMENT=production` and `JWT_SECRET` is still the known shipped default — a Pydantic
  validator, tested with both the refusal and the two cases that must NOT be blocked
  (development and test legitimately use a known secret on purpose).
- Security headers were checked directly and found genuinely absent, not just unverified —
  added on both backend (a new middleware, positioned as the outermost layer so headers
  land on error responses too, verified with a test) and frontend (`next.config.ts`'s
  `headers()`, verified live against a real running `next start` server).
- Two real graceful-shutdown gaps found by reading the actual library source code, not
  documentation: arq's own default is abrupt (`job_completion_wait: int = 0`, confirmed by
  reading `arq/worker.py` directly — below a truthy threshold it never even registers the
  graceful signal handler), while uvicorn's default is the opposite problem — unbounded,
  not bounded (`timeout_graceful_shutdown: int | None = None`, and `asyncio.wait_for`
  treats `None` as "wait forever", confirmed by reading `uvicorn/server.py`). Both fixed
  with an explicit, coordinated value, and confirmed `job_completion_wait` is a genuinely
  working `WorkerSettings` attribute by reading arq's own generic attribute-extraction
  mechanism (`get_kwargs()`), not assumed from a class attribute existing.
- `docker-compose.yml` resource limits verified via `docker compose config` to actually
  resolve correctly in normal (non-swarm) `docker compose up` — not assumed from general
  Compose Specification knowledge, checked directly against this exact file.
- Backup/restore scripts (`scripts/backup.sh`/`restore.sh`) pass `shellcheck` cleanly, and
  the underlying `pg_dump`/`psql`/`DROP DATABASE`/restore logic was genuinely tested end to
  end against this sandbox's real native Postgres (a test row survived a full dump →
  drop → recreate → restore cycle) — the `docker compose exec` wrapper itself couldn't be
  tested here, for the same registry-pull block as ADR-019, and that's stated plainly
  rather than implied to have been fully verified.
- What this pass deliberately doesn't cover, stated honestly rather than silently skipped:
  secrets management beyond a plain `.env` file (needs real infrastructure this project
  can't meaningfully demonstrate), a Content-Security-Policy (needs its own careful, tested
  pass — a rushed one is worse than none), and the broader security-hardening pass tracked
  separately since Phase 13 (a dedicated look for gaps *between* the piecemeal security
  tests already spread across many phases, which this audit found real things but wasn't).
