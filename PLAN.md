# Technical Implementation Plan

## Scope calibration (read this first)

The master prompt specifies a genuinely large system — 66 sections covering everything
a small team would build over a multi-month engagement. To do this honestly rather than
producing something that looks complete but isn't:

- I will build this **phase by phase, across multiple work sessions**, exactly as the
  master prompt's §2/§58 require — not attempt the whole system in one pass.
- Each phase ends with a real engineering report: what was implemented, what was tested,
  what passed/failed, what's deferred, and what needs your input or your machine to verify.
- Where this sandbox genuinely can't verify something (full Docker stack, GPU inference,
  real Postgres+Redis under load), I will say so explicitly rather than asserting it works.
- I have the authority (per §59) to make and document reasonable engineering calls via ADR
  without stopping to ask — already exercised for database, vector store, LLM abstraction,
  agent orchestration, and multi-tenancy strategy (see `docs/adr/`). I'll only stop to ask
  you directly when a decision needs information only you have (e.g. which cloud provider
  you'll actually deploy to, whether you have API keys for OpenAI/Anthropic/Gemini to test
  against, or a real company's actual document set for the demo).

## Phase sequence and what each produces

| Phase | Deliverable | Sandbox-verifiable here? |
|---|---|---|
| 0 | Environment inspection, CLAUDE.md, this plan | ✅ done |
| 1 | Architecture + ADRs | ✅ done (`docs/architecture/`, `docs/adr/`) |
| 2 | Backend + frontend scaffolding, repo structure, tooling (ruff/mypy/eslint) | ✅ |
| 3 | DB schema, Alembic migrations, auth (register/login/JWT/refresh), RBAC | ✅ fully — real PostgreSQL 16 installed via `apt` in this sandbox (no Docker needed for this), migrations applied, 24 tests passing against it, including tenant-isolation and RBAC tests |
| 4 | Upload API, file validation, background ingestion pipeline, status tracking | ✅ fully — real Redis + arq worker installed and run as a live separate process in this sandbox; genuine end-to-end smoke test (live HTTP upload → live worker dequeues from live Redis → real text extraction → status COMPLETED) confirmed working, not just unit-tested |
| 5 | Embedding provider abstraction + pgvector integration | ✅ real pgvector 0.6.0 + HNSW index installed and migrated in this sandbox; full chunking→embedding→storage→similarity-search pipeline verified against real Postgres using a test-only fake provider (huggingface.co is blocked + disk-constrained here — see ADR-008); live worker smoke test confirmed graceful failure handling when the real model genuinely can't load |
| 6 | Hybrid retrieval (semantic + tsvector) + reranking | ✅ real Postgres full-text search (GIN index) + real pgvector semantic search fused into `/api/v1/search`; reranking follows ADR-008's pattern (same sandbox constraint); live smoke testing found and fixed a real stack-trace-leak bug (`debug=True` default) |
| 7 | RAG pipeline, prompt construction with strict instruction/data separation, citation validation | ✅ real `AnthropicProvider`/`OllamaProvider` implemented; live-verified twice against the real Anthropic API (raw curl + our actual provider code, both got real structured 401s — no API key available, but connectivity and request-shape are genuinely proven, not mocked); full conversation/citation pipeline proven end-to-end via real HTTP API including hallucinated-citation rejection |
| 8 | Evaluation framework + golden dataset | ✅ fully — retrieval metrics (recall/precision/MRR/NDCG) verified against hand-computed textbook values; citation correctness is deterministic set comparison; LLM-judge for faithfulness/relevance follows the ADR-008/009/010 pattern; full harness (golden-dataset ingestion → real hybrid search → real RAG → metrics → DB persistence → baseline regression comparison) independently re-verified live in this sandbox against real Postgres, including confirming `python -m evaluation.run` completes cleanly and reports per-case failures accurately even when the underlying embedding model can't load |
| 9 | Agent state machine, MAX_STEPS/RUNTIME/TOOL_CALLS enforcement | ✅ fully — real deterministic state machine (ADR-005/012), 6 real tools spanning LOW/MEDIUM/HIGH risk with genuine human-approval gating for the destructive one; found and fixed 3 real SQLAlchemy relationship-sync bugs plus 1 test-infrastructure bug via independent testing against real Postgres; live-verified the agent's own failure handling (not just the generic safety net) against real unreachable infrastructure |
| 10 | Tool registry, risk classification, safe-SQL agent, permission checks | ✅ fully — audited Phase 9's tool system against spec §22/§23 and found 2 real gaps (not just documentation): a latent secrets-exposure risk (full Settings object, including API keys/JWT secret, reachable from every tool though unused by all of them) and a missing spec-required output_schema per tool; both fixed and independently verified (the output_schema fix proven to actually reject mismatched output via a deliberately misbehaving test tool, not just accept correct output); added draft_email tool + GET /api/v1/tools registry endpoint + agent-quality evaluation metrics (task success rate, tool selection accuracy, unnecessary tool calls), the last proven against a real deliberately-poorly-behaved agent run, not just a happy path |
| 11 | Structured logging, metrics endpoint, tracing hooks | ✅ fully — request-scoped correlation (request_id/user_id/organization_id) via contextvars + auto-injecting log filter; found and fixed a real BaseHTTPMiddleware context-isolation bug via live testing (rewrote as pure ASGI middleware); all 8 spec-named Prometheus metrics wired into real code paths and live-verified; "tracing where practical" scoped honestly to request-ID correlation across the API/worker process boundary (not full OpenTelemetry, since this is a monolith+worker, not microservices) and live-verified end-to-end with both processes running; closed a real Phase 8 structural gap found along the way (RagAnswer never exposed LLM token usage to callers at all); also closed a self-flagged gap (zero structured log lines anywhere in the agent system despite spec §29 requiring "tool calls" as a logged field) with real logging verified via a scripted end-to-end approval-flow test |
| 12 | Next.js frontend: auth, documents, chat with citations (agents/admin/analytics deferred — see below) | ✅ scoped and delivered — real UI on top of 11 backend-only phases; types generated from the backend's live OpenAPI schema, not hand-guessed; found and properly solved two permanent sandbox network constraints (fonts.googleapis.com and cdn.playwright.dev both blocked, same category as huggingface.co) rather than working around or silently skipping verification; tsc/eslint/build all clean from a from-scratch install; real HTTP verification against the live backend (API-client logic, citation-parsing including the hallucinated-citation edge case) since browser-based E2E isn't achievable in this sandbox — that gap is stated plainly, not hidden |
| 13 | Agent-run UI with human-approval gating (frontend continuation of Phase 12) | ✅ fully — start/list/detail views on top of the real synchronous agent backend (ADR-012); found and fixed a real type bug via live verification against the actual running server (`useStartAgentRun` was typed against the wrong response schema — a live check showed the real route returns `AgentRunDetailResponse`, not the summary-only `AgentRunResponse`); approval-detection logic verified against realistic schema-accurate data including two negative cases (an already-decided approval must not re-trigger the panel; a run with no tool calls must not show it); steps and tool calls render as two honest separate sections rather than a fabricated interleaved timeline, since the API genuinely has no field correlating one to the other (ADR-016) |
| 14 | Rate limiting and abuse prevention (spec §39) | ✅ fully — Redis-backed fixed-window limiter applied per-route (login, register, upload, search, chat, agent runs) plus a separate, tighter failed-login throttle keyed by email for real credential-stuffing protection; found and fixed a real bug in my own test-isolation setup (a conditional Redis flush was silently leaking rate-limit counters across tests); found and properly fixed a significant pre-existing gap dating to Phase 2 (the global HTTPException handler claimed a consistent error shape but didn't deliver one — verified safe app-wide, 279 tests still passing) that turned out to have been silently breaking real frontend error messages since Phase 12; found and fixed a third bug in the failed-login throttle's own metric emission via live testing against a real server |
| 15 | Admin and evaluation dashboards (surfacing Phase 8 evaluation runs + Phase 11 Prometheus metrics) | ✅ fully — platform-wide (deliberately not org-scoped) evaluation browsing plus a live metrics snapshot honestly labeled as "since server start," not a fabricated historical chart; verified live end-to-end (an admin of a freshly-registered, unrelated org could see an evaluation run belonging to Phase 8's throwaway system org, exactly as ADR-018 designed); frontend nav gating checks the identical condition as the backend's access-control dependency, confirmed via the same live-E2E-script pattern used since Phase 12 |
| 16 | Docker Compose (all 5 services: postgres, redis, api, worker, frontend) | ✅ fully — found a genuinely new class of sandbox constraint (the Docker daemon itself runs here, but registry-1.docker.io is blocked, confirmed via a real `403` on `docker pull`); did the strongest verification actually achievable (`docker compose config` genuinely parses and validates the full compose file — service hostnames, health-check conditions, build-arg wiring, shared volumes — not a rubber-stamp); found and fixed a real, previously undiscovered bug in `.env.example` (`NEXT_PUBLIC_API_BASE_URL` included a `/api/v1` suffix the frontend code also appends itself, which would have silently 404'd — never caught in five prior phases since this variable was never actually set explicitly until Docker Compose required it) |
| 17 | README, architecture docs, ADRs, benchmarks | Partial — ADRs genuinely delivered throughout (19 of them, one per real decision, written the same phase the decision was made); a minimal, scoped README landed as part of Phase 16 (just enough to make Docker Compose discoverable); a fuller README pass and actual benchmark numbers remain undelivered — see known gaps |
| 18 | Production-readiness audit (backups, secrets, graceful shutdown, resource limits, dependency vulnerabilities) | ✅ fully — a real `pip-audit`/`npm audit` run found genuine CVEs across 8 packages; every upgrade empirically tested (full test suite + ruff + mypy) in an isolated venv before adoption, including confirming a patched `starlette` is genuinely incompatible with the old pinned `fastapi` before jumping FastAPI 26 minor versions ahead — zero known vulnerabilities afterward, confirmed by re-scanning, not assumed; two real graceful-shutdown gaps found by reading arq's and uvicorn's actual source code (both default to the wrong behavior in opposite directions) and fixed with coordinated, explicit values; a real production-safety guard added (refuses to start with the default JWT secret in production); security headers added on both backend and frontend, verified live; backup/restore scripts with the underlying SQL logic genuinely tested end to end |

## Known gaps carried forward (not hidden, tracked here)

- OCR for scanned/image-only PDFs is not implemented (would need `poppler` +
  page rasterization) — such a PDF fails extraction with a clear reason
  rather than silently returning empty text.
- No admin-invite flow yet for granting another user a role in an
  organization — RBAC tests had to insert memberships directly via the DB.
- No rate limiting yet on `/documents` upload, `/search`, or
  `/conversations/*/messages` (spec §39) — deferred at least four times now
  (Phases 4, 6, 10, and again here when Phase 13's slot went to agent UI
  instead). Genuinely overdue at this point, not just noted in passing.
- A dedicated security-hardening pass (injection tests beyond what's
  already covered piecemeal — SQL injection via the safe-SQL tool's
  validation tests, prompt injection structure tests, tenant-isolation
  tests throughout — plus a focused upload-hardening audit) doesn't have
  its own phase anymore now that Phase 13's slot went to agent UI instead.
  Not silently dropped: real security testing exists distributed across
  many phases' test suites, but a single, deliberate pass specifically
  looking for gaps *between* those piecemeal tests hasn't happened.
- Neither the real `sentence-transformers` embedding provider nor the real
  `CrossEncoderReranker` has ever actually run end-to-end anywhere (blocked
  network + disk budget — see ADR-008, ADR-009). A real, authenticated LLM
  completion also hasn't run anywhere — this sandbox has no API key (though
  connectivity and our request-building code are genuinely live-verified,
  see ADR-010). All three need your machine (or a key) to fully confirm.
- Genuine behavioral prompt-injection-resistance (does a real model actually
  refuse an embedded instruction?) is NOT proven — only that the prompt is
  structurally well-formed. This needs a real API key to test properly.
- No streaming responses yet (spec §19 mentions this) — the RAG endpoint
  returns a single complete JSON response. A deliberate scope cut to keep
  this phase's size manageable; streaming is additive on top of the current
  design (the LLMProvider protocol would need a `stream()` method), not a
  redesign.
- Conversations are visible to all org members, not just their creator —
  deletion is restricted to ADMIN/MANAGER. A reasonable default for now;
  revisit if per-user-private conversations become a real requirement.
- Chunking is character-based (not token-aware) — reasonable, common
  approach, revisit if needed.
- Regression detection (spec §28) is purely relative to the previous run —
  if a metric is already at its worst possible value (e.g. error_rate=1.0),
  staying there isn't flagged as a regression, since nothing got *worse*.
  Found this live: two consecutive runs with a completely broken embedding
  provider correctly reported "no regressions" despite 100% failure. A
  complementary absolute sanity threshold (e.g. fail if error_rate exceeds
  some hard cap regardless of baseline) would close this gap — worth adding
  before this becomes a real CI gate, not urgent for the current phase.
- Agent execution is synchronous within the HTTP request, not a background
  job (ADR-012 decision 2) — bounded by MAX_STEPS/MAX_RUNTIME_SECONDS so
  this stays reasonable, but a long-running or many-step workflow would
  benefit from arq-based background execution with proper resumability.
  Deliberate scope cut, not an oversight — the state machine design doesn't
  need to change to add this later, only how it's scheduled.
- The safe-SQL tool's table/keyword validation uses regex, not a proper SQL
  parser (e.g. sqlglot) — acceptable because the database-enforced read-only
  transaction (layer 4) is the safety guarantee that actually matters if the
  regex layers have a gap, but a real parser would be a reasonable upgrade
  for the string-level layers specifically.
- Agent evaluation now covers 3 of spec §27's 6 listed agent metrics (task
  success rate, tool selection accuracy, unnecessary tool calls) — added in
  Phase 10. Tool argument correctness, failure recovery, and a
  completion-rate metric distinct from success rate are not implemented;
  the first is largely already covered by Tool.run()'s Pydantic input
  validation (Phase 9), the other two are genuine gaps worth a focused
  follow-up, not silently dropped.
- The agent evaluation metrics aren't wired into the `python -m
  evaluation.run` CLI as a first-class `--agents` flag — verified instead
  via a dedicated integration test proving the metrics work against real
  AgentService runs. Wiring into the CLI is a reasonable follow-up once the
  RAG and agent evaluation reports have an obvious reason to be unified.
- MODEL_COST/token-usage tracking (Phase 11) covers per-call estimation via
  Prometheus counters and per-evaluation-case metrics, but there's no
  persisted, queryable cost history or budget/alerting for real production
  usage (spec §31's fuller cost-tracking scope) — a natural extension once
  there's an admin surface to show it in.
- Frontend (Phase 12) deliberately covers only the core RAG loop (auth,
  documents, chat with citations) — no agent-run UI (starting a run,
  watching it progress, approving/rejecting a HIGH_RISK tool call) and no
  admin/evaluation dashboards, collection management, or member/role
  management UI. See ADR-015 decision 6 for the full reasoning.
- Frontend has no automated browser-based test coverage — Playwright's
  Chromium download is blocked by this sandbox's network allowlist
  (`cdn.playwright.dev`), the same category of constraint as
  `huggingface.co`/`fonts.googleapis.com`. Verified instead via `tsc`/
  `eslint`/`next build` (all clean) and real HTTP requests against the live
  backend replicating the frontend's exact data-layer logic — but actual
  visual rendering and click-through interaction are unverified in this
  sandbox and need a real browser to confirm.
- Frontend auth tokens are stored in `localStorage` (ADR-015 decision 4),
  the standard trade-off for a bearer-JWT SPA without backend cookie
  support — a production deployment handling more sensitive data would
  likely want the backend to move to httpOnly cookies instead.
- Agent UI (Phase 13) shows steps and tool calls as two separate sections
  rather than one interleaved timeline, because the API doesn't expose a
  field correlating a specific step to a specific tool call, or a
  timestamp on tool calls to sort them against steps (ADR-016 decision 2).
  A real, worthwhile backend follow-up: add `tool_call_id` to
  `AgentStepResponse` and `created_at` to `ToolCallResponse` so the
  frontend can show a genuinely accurate combined timeline instead.
- No automated browser-based verification of the agent-run/approval UI for
  the same reason as Phase 12 — `cdn.playwright.dev` is blocked in this
  sandbox. Verified via `tsc`/`eslint`/`build` (clean), a live E2E check
  against the real running backend, and standalone verification of the
  approval-detection logic against realistic data — but the actual visual
  approval panel, its button styling, and the click flow are unverified
  here and need a real browser to confirm.
- "Full automated test suite" (this slot's original placeholder content)
  didn't get its own dedicated phase, same as Phase 13's displaced
  "security hardening pass" note — but unlike that case, this genuinely
  has been achieved incrementally: 292 backend tests (as of Phase 15) plus
  frontend `tsc`/`eslint` checks, built up across every phase's own test
  file throughout the project, not deferred to a single later pass.
- Rate limiting (Phase 14) uses fixed-window counters with a documented,
  accepted boundary-burst limitation (ADR-017 decision 1) — a caller can
  get up to ~2x the stated limit in a short burst straddling two adjacent
  windows. A sliding-window-log would close this but adds real complexity
  (unbounded-looking sorted-set growth, more Redis round-trips) not
  justified without evidence the boundary case matters in practice.
- Rate limit thresholds are configurable but not currently exposed through
  any admin UI — changing them requires an environment variable change and
  restart, not a runtime admin action. The admin dashboard (Phase 15) adds
  *viewing* platform health, not *configuring* it — a real, worthwhile
  follow-up now that there's a real admin surface to add it to.
- Docker Compose (Phase 16) is delivered, but genuinely verified only up to
  what this sandbox allows — `docker compose config` proves the file is
  structurally correct, but an actual `docker compose up --build`, building
  both images and running the five-service stack end to end, needs a
  machine with normal Docker registry access (`registry-1.docker.io` is
  blocked here — see ADR-019 decision 5). Stated plainly, not implied to
  have happened in this sandbox.
- Production-readiness (Phase 18/ADR-020) is delivered, but with real,
  stated limits: no Content-Security-Policy yet (needs its own careful,
  tested pass — a rushed CSP is worse than none), secrets still live in a
  plain `.env` file (a real secrets manager is genuinely out of scope
  without infrastructure this project can't demonstrate running), and the
  30s graceful-shutdown window won't fully protect an in-flight agent run
  (which can legitimately run up to 90s, ADR-012) — a real, acknowledged
  trade-off between shutdown speed and in-flight-request safety, not an
  oversight.
- Backup/restore scripts (Phase 18) had their underlying SQL logic
  genuinely tested end to end, but the `docker compose exec` wrapper
  around that logic couldn't be — the same registry-pull block noted for
  Docker Compose itself (ADR-019). Stated plainly, not implied to have
  been fully verified.
- The README stays deliberately minimal — scoped to a quick start and
  pointers, not a comprehensive project doc. That fuller documentation now
  exists as three separate, focused guides (`SETUP_GUIDE.md`,
  `EXECUTION_GUIDE.md`, `IMPLEMENTATION_GUIDE.md`), added on request after
  Phase 18, each cross-checked against the actual current codebase (real
  table names, real ADR filenames, real config/env-var names) rather than
  written from memory of building it. Actual performance benchmark numbers
  (this project's own §63-adjacent placeholder content) still have never
  been measured at all — no numbers exist to report, invented or
  otherwise, which is itself the honest state to leave this in until real
  benchmarking happens.
- The admin dashboard (Phase 15) shows evaluation runs and a metrics
  snapshot, but nothing about agent runs or documents platform-wide across
  organizations — an admin can only see agent/document activity within
  their own org's normal views, not a cross-org operational view. Not
  addressed here; would need its own design decision about whether
  cross-org visibility into customer data is even appropriate for an
  org-ADMIN-proxied access model (see ADR-018 decision 1's stated
  limitation) rather than assumed safe to add later.

## Immediate next step

Two real candidates, not yet decided between: the security-hardening pass
still separately tracked since Phase 13 (a dedicated look for gaps
*between* the piecemeal security tests already spread across many phases —
this audit found and fixed real things but wasn't that focused pass), and
a Content-Security-Policy for the frontend (deliberately deferred in
ADR-020 rather than rushed). The security-hardening pass has the stronger
claim, being tracked and displaced twice now (Phase 13's slot, then noted
again here) — genuinely overdue.

## Resolved decisions

- LLM provider for development: Claude (paid subscription available) rather
  than Ollama-only — the provider abstraction (ADR-004) still supports both;
  Ollama remains the default for anything that should stay fully local/free,
  but Claude is available and preferred for actual RAG/agent development.
- Scope: portfolio project for a personal profile, not a literal client
  handoff — informs choices like local filesystem storage being an
  acceptable stand-in for S3-compatible object storage for now.
