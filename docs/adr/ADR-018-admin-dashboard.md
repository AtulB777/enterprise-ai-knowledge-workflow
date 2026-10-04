# ADR-018: Admin and Evaluation Dashboards

**Status:** Accepted

## Context
Phase 8 built real evaluation runs persisted to Postgres; Phase 11 built
real Prometheus metrics. Neither had anywhere a human could actually look
at them — evaluation data only via `python -m evaluation.run`'s console
output or direct SQL, metrics only via a raw `/metrics` scrape. This phase
gives both a real UI.

## Decision 1: admin access is "ADMIN role in at least one organization," not a new platform-admin role
This app has no separate platform/superadmin concept — only org-scoped
roles (VIEWER/EMPLOYEE/MANAGER/ADMIN, per-organization). Building a genuine
platform-admin role system (a new table, a new concept orthogonal to
organization membership entirely) is real, valid future work, but is a
larger scope addition than this phase's actual goal — showing eval/metrics
data to a reasonably trusted user. The pragmatic choice: gate the new admin
routes behind "the authenticated user holds ADMIN in at least one
organization they belong to," reusing the existing role system as a proxy
for "trusted enough to see platform-wide operational health." Stated
plainly as a scope decision, not silently assumed: a real production
deployment with many customer orgs would likely want genuine platform-admin
accounts, separate from any specific org's ADMIN role.

## Decision 2: the evaluation dashboard is genuinely platform-wide, not org-scoped
`EvaluationRun.organization_id` is a real, non-nullable column — but it
points at the throwaway `evaluation-dataset` organization Phase 8's runner
creates (system/dev data, not customer data — see ADR-011). A regular
customer organization's admin would never have evaluation runs under their
own `organization_id`; scoping the dashboard the way every other endpoint
in this app is scoped (`WHERE organization_id = :current_org`) would show
an empty list for every real admin, always. New, deliberately
un-tenant-scoped repository methods (`list_all_runs`, `get_run_by_id_any_org`)
back the admin endpoints — the existing org-scoped methods stay as they are
for any future per-org evaluation use case, not replaced.

## Decision 3: the metrics dashboard is an honest "current process snapshot," not a historical chart
Prometheus counters live in-process (`prometheus_client`'s in-memory
registry) — cumulative since this specific server process started, with no
persisted time-series history. A real historical dashboard needs an actual
Prometheus server polling and storing samples over time, plus something
like Grafana to chart them — genuine additional infrastructure this
project doesn't run (CLAUDE.md §60's anti-overengineering principle: not
justified for a portfolio project's scale, and not something this sandbox
could demonstrate running anyway). Rather than build a dashboard that
*implies* historical trends it can't actually show, `GET /api/v1/admin/
metrics-summary` returns a clearly-labeled current snapshot (read from the
same live registry `/metrics` already exposes, via `prometheus_client`'s
own collection API — not a second, parallel counting mechanism) and the
frontend labels it as such ("since this server started"), rather than
rendering a line chart that would misrepresent single point-in-time values
as a trend.

## Decision 4: routes and pages
- `GET /api/v1/admin/metrics-summary` — the snapshot above.
- `GET /api/v1/admin/evaluations` — paginated list of all evaluation runs.
- `GET /api/v1/admin/evaluations/{run_id}` — one run's summary metrics plus
  every per-case `EvaluationResult`.
- `/admin` (metrics snapshot + a link into evaluations), `/admin/evaluations`
  (list), `/admin/evaluations/[runId]` (detail) — a new frontend nav entry,
  shown only when the signed-in user's memberships include at least one
  ADMIN role, matching Decision 1's backend gate exactly so the UI doesn't
  offer a link a request would then reject.

## Consequences
- No new database tables — this phase is entirely new read paths over data
  Phases 8 and 11 already produce for real, not a new data model.
- The `/admin` prefix is deliberately outside per-organization query-param
  scoping (`?organization_id=...`) that the rest of the API uses — these
  routes take no organization_id at all, reinforcing that they're
  platform-level, not tenant-level.
