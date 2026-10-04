# ADR-002: Vector Search Architecture

**Status:** Accepted

## Context
Spec requires choosing exactly one primary vector database: PostgreSQL+pgvector or Qdrant.

## Decision
`pgvector` extension on the primary PostgreSQL instance.

## Alternatives considered
**Qdrant** — purpose-built, very good ANN performance and filtering at scale, but:
- adds a second service to run, secure, back up, and monitor
- adds a second place where tenant isolation must be independently enforced
- not justified at the document/chunk volumes this platform starts at

## Reasoning
- Keeps tenant isolation enforcement in one place (Postgres row-level filtering via
  `organization_id`), rather than duplicating the isolation logic across two databases.
- One connection pool, one migration system, one backup story.
- `pgvector` supports HNSW/IVFFlat indexes, which is sufficient for the target scale
  (an enterprise knowledge base, not a web-scale consumer vector search product).

## Trade-offs
- Ceiling on raw ANN throughput/latency below a dedicated vector DB at very high scale.
- Index build/maintenance shares resources with the transactional workload.

## Consequences
- Retrieval code sits behind a `VectorStore` repository interface so swapping to
  Qdrant later — if evaluation/benchmark data (Phase 63) shows a real need — is a
  contained change, not a rewrite of the RAG pipeline.
- Embedding dimension and index type are recorded in `document_chunks` metadata so
  re-indexing on model change (section 14) is tractable.
