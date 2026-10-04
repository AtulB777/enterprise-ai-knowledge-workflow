# ADR-020: Production-Readiness Audit

**Status:** Accepted

## Context
The displaced placeholder from Phase 16's slot, and a natural fit now that
the whole stack — backend, worker, frontend, and how to deploy all three
together — is real and complete. This is an audit, not a feature phase: the
goal was to find real gaps and either fix them or document them honestly,
not to pad the codebase with checklist theater.

## Decision 1: a real dependency vulnerability audit, every fix empirically tested before adopting
Ran `pip-audit` against the real, live vulnerability database (not a
simulated or assumed check) and found genuine CVEs in `fastapi`/
`starlette` (transitive)/`pyjwt`/`python-multipart`/`pypdf`/`pillow`.
`npm audit` found real findings in `eslint`/`postcss` (frontend build
tooling, not runtime code shipped to browsers, but still worth fixing).

Every upgrade was tested before being adopted, not blindly version-bumped:
- Confirmed directly that `starlette>=0.47.2` (a patched version) is
  genuinely incompatible with the pinned `fastapi==0.115.6`
  (`fastapi 0.115.6 requires starlette<0.42.0,>=0.40.0` — pip's own
  resolver said so).
- Tested the *latest* FastAPI (0.141.1, twenty-six minor versions ahead of
  the pin from Phase 2) in an isolated venv against this project's real
  292-test suite, `ruff`, and `mypy` — all clean — before adopting it.
  Same rigor for the `pypdf`/`pillow` major-version bumps.
- Result: zero known vulnerabilities across the entire backend dependency
  set and the frontend's `npm audit`, both confirmed by re-running the
  scanners after the fix, not assumed from the version bump alone.

## Decision 2: two real bugs the upgrade itself surfaced, both fixed
The FastAPI/Starlette upgrade produced two real warnings during the
verification test run, not silently ignored:
- `HTTP_422_UNPROCESSABLE_ENTITY` is deprecated in the newer Starlette in
  favor of `HTTP_422_UNPROCESSABLE_CONTENT` (same numeric value, 422 —
  confirmed before renaming, not assumed) — both usages updated.
- The newer PyJWT warns (`InsecureKeyLengthWarning`) on HMAC keys under 32
  bytes per RFC 7518 §3.2 — one test used an 11-byte placeholder secret.
  Fixed to a properly-length value; this was never a production issue
  (the real, documented `JWT_SECRET` generation via `openssl rand -hex 32`
  already produces 32 bytes), but worth respecting the new signal anyway.

## Decision 3: refuse to start in production with the known default JWT secret
A real, meaningful safety net, not just documentation telling people to
change it: `Settings` now has a `model_validator` that raises if
`environment == "production"` and `jwt_secret` still equals the shipped
default. Scoped specifically to `production` — `development` and `test`
both legitimately use a known, shared secret on purpose, and must not be
blocked (verified with tests covering both the refusal and these two
explicit non-refusal cases).

## Decision 4: security headers, genuinely absent before this phase
Checked directly and found none — not "unverified," actually missing.
Added on both sides:
- Backend: a new `SecurityHeadersMiddleware`, registered as the outermost
  layer specifically so the headers land on error responses too (verified
  with a test asserting they're present on both a 200 and a 422). Most
  valuable for the real HTML FastAPI's own `/docs` (Swagger UI) serves.
- Frontend: `next.config.ts`'s `headers()` — the actual user-facing HTML
  people load in a browser, arguably more important than the backend's own
  headers for real security posture. Verified live against a real running
  `next start` server, not just asserted from the config.

`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` (this API/app
has no legitimate framing use case), `Referrer-Policy:
strict-origin-when-cross-origin`, `Permissions-Policy` denying geolocation/
camera/microphone (nothing here uses them). No `Content-Security-Policy`
added yet — a real CSP needs to be built against the actual script/style
sources in use and tuned carefully to avoid breaking legitimate
functionality; a rushed, untested CSP is worse than none. Tracked as a
real follow-up in PLAN.md, not silently added half-considered.

## Decision 5: CORS was already configurable, just undocumented
`cors_allow_origins` already existed as a real setting (Phase 2) with a
safe default (a specific origin, not a wildcard — `allow_credentials=True`
combined with a wildcard origin is both insecure and something browsers
reject outright, so the existing default was never actually at risk here).
The gap was purely that `.env.example` never mentioned it. Documented now,
with the exact JSON-array parsing behavior verified directly
(`CORS_ALLOW_ORIGINS='["a","b"]'` → `['a', 'b']`) before writing it down,
not assumed from pydantic-settings' general behavior.

## Decision 6: graceful shutdown — both real gaps found by reading the actual library source, not documentation
- **arq (worker)**: its own default is abrupt, not graceful —
  `job_completion_wait: int = 0` in `Worker.__init__`, confirmed by reading
  `arq/worker.py` directly. Below a truthy threshold, arq registers the
  abrupt `handle_sig` signal handler instead of `handle_sig_wait_for_completion`.
  `app/workers/settings.py` now explicitly sets `job_completion_wait = 30`
  — confirmed as a genuinely working `WorkerSettings` attribute by reading
  arq's `get_kwargs()` (a generic mechanism reading any class attribute
  matching a `Worker.__init__` parameter name), not assumed.
- **uvicorn (api)**: its default is the *opposite* problem — unbounded
  (`timeout_graceful_shutdown: int | None = None`, and `asyncio.wait_for`
  treats `None` as "wait forever"), confirmed by reading `uvicorn/server.py`
  directly. In an orchestrated environment this just means Docker's own
  blunt SIGKILL becomes the real enforcement mechanism instead of a clean
  shutdown. Set explicitly to 30s in `backend/Dockerfile`'s `CMD`.
- Both coordinated with `docker-compose.yml`'s `stop_grace_period: 35s` for
  `api`/`worker` (slightly longer than each service's own 30s wait, so
  Docker's SIGKILL doesn't land right at the boundary and cut off the
  app's own clean-exit logic).
- Stated honestly, not glossed over: 30s won't fully protect an in-flight
  agent run, which can legitimately run up to `MAX_RUNTIME_SECONDS` (90s,
  ADR-012). A longer graceful window would protect that case better at the
  cost of slower deploys/restarts generally — a real trade-off, not an
  oversight.

## Decision 7: resource limits added to every `docker-compose.yml` service
`deploy.resources.limits` (verified via `docker compose config` to
actually resolve correctly in normal, non-swarm `docker compose up` — the
Compose Specification applies this, unlike older `docker-compose` v1 with
a `version: "3"` file, where it required swarm mode). Sized by what each
service actually does: `api`/`worker` get more (2 CPU / 2GB) since both
load a real embedding model in-process (ADR-008); `postgres` gets 1 CPU /
1GB; `redis` and `frontend` get less, having no comparable in-process
workload.

## Decision 8: real backup/restore scripts, the SQL commands genuinely tested
`scripts/backup.sh` / `scripts/restore.sh` — `pg_dump`/`psql` run inside
the `postgres` container via `docker compose exec` (so they always match
whatever server version is actually deployed, not a possibly-mismatched
host-installed `pg_dump`). `restore.sh` is destructive (drops and
recreates the target database) and requires typing the database name to
confirm before doing anything, not just a bare "are you sure? y/n".

Both scripts pass `shellcheck` cleanly. The actual SQL logic (`pg_dump`,
then `DROP DATABASE` / `CREATE DATABASE` / restore) was genuinely tested
end to end against this sandbox's real native Postgres — created a test
database, inserted a real row, dumped it, dropped and recreated the
database, restored from the dump, confirmed the row survived — since the
`docker compose exec` wrapper itself couldn't be tested here (the same
registry-pull block as ADR-019). The underlying database operations these
scripts perform are proven correct; the Docker-specific wrapping around
them is not further verified beyond what `docker compose config` already
confirms about the service names these scripts reference.

## What this pass deliberately does not cover
- **Secrets management beyond a plain `.env` file.** A real production
  deployment handling actual sensitive data should use a proper secrets
  manager (AWS Secrets Manager, Vault, Docker secrets) — genuinely out of
  scope for what this project can meaningfully demonstrate without that
  infrastructure actually running somewhere. The production JWT-secret
  guard (Decision 3) is the one piece of this that's directly actionable
  in code; the rest is a real, stated limitation, not silently ignored.
- **A Content-Security-Policy** (see Decision 4) — needs its own careful,
  tested pass, not a rushed addition here.
- **The security-hardening pass tracked since Phase 13** — a broader,
  dedicated look specifically for gaps *between* the piecemeal security
  tests already spread across many phases' test suites. This audit found
  and fixed real things, but wasn't that dedicated pass; still tracked
  separately in PLAN.md.
