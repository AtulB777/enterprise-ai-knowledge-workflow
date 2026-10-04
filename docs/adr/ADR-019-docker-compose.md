# ADR-019: Docker Compose

**Status:** Accepted

## Context
Genuinely undelivered until now — confirmed via direct search in Phase 15
that no `docker-compose.yml` or `Dockerfile` existed anywhere in this repo.
Running this stack meant manually starting Postgres, Redis, the API, the
worker, and the frontend dev server as five separate processes, per
CLAUDE.md's own setup instructions.

## Decision 1: `pgvector/pgvector:pg16`, not plain `postgres:16` + a manual `apt install`
The real image the pgvector project publishes specifically for this
purpose — Postgres 16 with the pgvector extension's files already present,
so the existing `1e6a7533ea17` migration's `CREATE EXTENSION vector` just
works, with no extra install step baked into the compose file or a custom
Postgres image of our own to maintain.

## Decision 2: one backend image, two services — `api` runs migrations then serves; `worker` waits for `api` to be healthy, then runs arq
Both `api` and `worker` build from the same `backend/Dockerfile` — the
worker service simply overrides the default `CMD` with `arq
app.workers.settings.WorkerSettings`. Only `api`'s entrypoint runs `alembic
upgrade head` before starting uvicorn, and `worker` depends on `api` with
`condition: service_healthy` (not just `service_started`) — this avoids a
real race condition two services both running `alembic upgrade head`
concurrently on first boot could otherwise hit, without needing a separate
one-off migration container to coordinate. A real production deployment
would more likely run migrations as a distinct CI/CD step, not on every
container start — noted here as a deliberate dev/demo-appropriate trade-off,
not asserted as the right choice for every deployment shape.

## Decision 3: `NEXT_PUBLIC_API_BASE_URL` is a build arg, not a runtime environment variable
A real, easy-to-get-wrong Next.js/Docker interaction: `NEXT_PUBLIC_*`
variables are inlined into the client JavaScript bundle at `next build`
time, not read from the container's environment at runtime — setting it
only under `environment:` in `docker-compose.yml` would silently do
nothing, since by the time the container starts, the value is already
baked into static files that were built without it. `frontend/Dockerfile`
declares `ARG NEXT_PUBLIC_API_BASE_URL` before the build stage, and
`docker-compose.yml` passes it via `build.args`, not `environment`. It
defaults to `http://localhost:8000` — the URL the *browser* (running on the
host machine, outside the Docker network) needs, not the internal
`http://api:8000` service hostname a container-to-container request would
use, which would be the wrong value entirely here.

## Decision 4: multi-stage builds for both images, `output: "standalone"` for the frontend
Both Dockerfiles separate a build stage (full toolchain: pip/npm, compilers
for any native deps) from a slim runtime stage (just the installed
artifacts + application code), and both run as a non-root user in the
final stage. `next.config.ts` now sets `output: "standalone"`, which makes
`next build` trace and copy only the `node_modules` entries actually
needed at runtime into `.next/standalone` — avoiding shipping the full
`node_modules` tree (including `devDependencies` like the openapi-typescript
CLI, unnecessary at runtime) into the final image.

## Decision 5: verification — the daemon runs here, but registry pulls don't; documented honestly, not glossed over
This sandbox has no `docker` binary by default, unlike every other tool
used throughout this project. Installed it via `apt` (`docker.io`,
`docker-compose-v2` — both present in the standard Ubuntu repos already
reachable here) and found something genuinely worth noting: the daemon
itself starts and runs correctly (`docker ps` responds normally). What
doesn't work is pulling base images — `registry-1.docker.io` isn't in this
sandbox's network allowlist, confirmed directly (`docker pull
postgres:16-alpine` returns a real `403 Forbidden`), the same category of
permanent, environment-level constraint as `huggingface.co`,
`fonts.googleapis.com`, and `cdn.playwright.dev` being blocked in earlier
phases — not a Docker Compose configuration problem to work around.

What *was* genuinely verified here, not just asserted: `docker compose
config` (bundled with `docker-compose-v2`) fully parses and validates
`docker-compose.yml` — service definitions, `depends_on` conditions,
volume mounts, build-arg wiring, and `.env` variable interpolation — all
without needing to reach any registry. This caught real, fixable issues
before delivery (see the CLAUDE.md changelog for specifics), the same way
`tsc`/`ruff`/`mypy` catch real issues elsewhere in this project — this
wasn't a rubber-stamp check. A full `docker compose up --build`, actually
building both images and running the five-service stack end to end, needs
a machine with normal registry access — stated plainly, not implied to
have happened here.

## Consequences
- Root-level `.env.example` (distinct from `backend/.env.example`) holds
  the variables `docker-compose.yml` itself interpolates (`POSTGRES_PASSWORD`,
  `JWT_SECRET`, `ANTHROPIC_API_KEY`, etc.) — copy it to `.env` before running
  `docker compose up`, matching the existing `backend/.env.example` /
  `backend/.env` convention this project already uses.
- `backend/Dockerfile` installs the real, complete `requirements.txt` —
  including `sentence-transformers` — unlike every `pip install` this
  sandbox itself has run throughout the project (which always excluded it
  for disk-space reasons). The Docker image is the actual, intended
  deployment artifact; the sandbox's own exclusion was always a sandbox-only
  workaround, never something that belonged in the real Dockerfile.
