# ADR-006: Multi-Tenancy Strategy

**Status:** Accepted

## Context
Multiple organizations must use the system with zero data leakage between them.

## Decision
Shared schema, shared database, with `organization_id` as a required, indexed,
non-null foreign key on every tenant-owned table — enforced at the **repository
layer**, not left to individual query call sites.

## Alternatives considered
- **Schema-per-tenant:** stronger physical isolation, but multiplies migration
  operations and connection management complexity for no added security if the
  shared-schema approach is enforced and tested correctly. Reconsider only if a
  customer's compliance requirements demand physical separation.
- **Database-per-tenant:** same trade-off, worse operationally, ruled out at this stage.

## Reasoning
- Shared schema with enforced filtering is the industry-standard approach for
  this scale of SaaS platform and keeps migrations, backups, and connection pooling
  simple — one of everything instead of N.
- Centralizing the filter in the repository layer (rather than trusting every
  endpoint/service to remember `WHERE organization_id = ...`) means a missed filter
  is a code-review-catchable pattern violation, not a silent per-endpoint bug.

## Trade-offs
- A single repository-layer bug could, in principle, affect multiple tenants — this
  is why section 36's cross-tenant access tests are treated as mandatory, not optional,
  and run against every tenant-scoped endpoint.

## Consequences
- Every new repository method for a tenant-owned entity takes `organization_id` as a
  required parameter by convention (enforced in code review / a lint rule where
  feasible), never an optional filter.
- Automated tests attempting cross-tenant reads/writes are part of the standard test
  suite for every tenant-scoped endpoint, not a separate "security testing" afterthought.
