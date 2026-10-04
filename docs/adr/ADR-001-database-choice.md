# ADR-001: Database Choice

**Status:** Accepted

## Context
Need a primary datastore for relational data (users, orgs, documents, conversations,
agent runs, audit logs) that also supports multi-tenancy, strong consistency for
auth/permissions, and can be extended for vector + full-text search (see ADR-002).

## Decision
PostgreSQL as the single primary datastore for all relational, vector (via `pgvector`),
and full-text (via native `tsvector`) needs.

## Alternatives considered
- **MySQL/MariaDB:** weaker native JSON/array/full-text tooling for this use case; no
  first-class vector extension as mature as pgvector.
- **MongoDB:** would fit document metadata but fights the relational integrity needs
  (foreign keys across org/user/permission/audit tables) and adds a second query
  paradigm for no real benefit here.
- **Split stores (Postgres for relational + separate vector DB + separate search
  engine):** evaluated and rejected as the default — see ADR-002.

## Reasoning
- Mature, well-understood, strong ACID guarantees for auth/RBAC/audit data where
  correctness matters most.
- `pgvector` and native full-text search remove the need for two extra services in a
  system that already has to run on a modest local dev machine.
- Alembic migrations give a single, auditable schema history.

## Trade-offs
- pgvector is not as fast at very large vector volumes/high QPS as a purpose-built
  vector DB (Qdrant, etc.). Acceptable at the scale this platform targets initially.
- Full-text search via `tsvector` is less feature-rich than OpenSearch/Elasticsearch
  (no built-in analyzers ecosystem, no distributed scaling). Acceptable per ADR-002/
  section 15 guidance to avoid introducing a search engine unless justified.

## Consequences
- One service to run, back up, and secure in local dev and early production.
- If vector volume or query load later exceeds what pgvector handles well, migrating
  to Qdrant is a contained change behind the retrieval repository interface, not a
  system-wide rewrite.
