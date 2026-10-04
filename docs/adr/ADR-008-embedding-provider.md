# ADR-008: Embedding Provider

**Status:** Accepted

## Context
Need embeddings for RAG retrieval. CLAUDE.md already committed (Phase 2) to
"a lightweight model suitable for the development machine" with
`all-MiniLM-L6-v2` named as the default. Must support the same
local-vs-cloud swappability principle as ADR-004's LLM provider abstraction.

## Decision
`EmbeddingProvider` protocol (`app/services/embeddings/provider.py`) with
`SentenceTransformersEmbeddingProvider` (`all-MiniLM-L6-v2`, 384 dimensions)
as the default, real implementation — confirming the Phase 2 decision rather
than revisiting it, per §59 (no reason has emerged to change it).

## A note on how this was verified (read this before assuming CI parity)
This sandbox's egress proxy blocks `huggingface.co` outright
(`x-deny-reason: host_not_allowed`), and separately, `sentence-transformers`'
PyTorch dependency exhausted this sandbox's disk budget when installed. Both
are sandbox-specific limits, not application problems — your actual
development machine has normal internet access and more disk headroom.

Given that, verification here follows the same honest split used for Docker
(Phase 0) and Ollama/OpenAI/Anthropic LLM calls (deferred to Phase 7):
- `SentenceTransformersEmbeddingProvider`'s own wrapper logic (batching,
  dimension validation, recording `embedding_model` on each chunk, running
  the blocking `.encode()` call via `asyncio.to_thread`) is unit-tested by
  mocking the `sentence_transformers` import boundary — the import is
  deliberately lazy (inside the method, not the module top level) specifically
  so this works without the real package installed in this sandbox.
- The full chunking → embedding → pgvector storage → similarity retrieval
  pipeline is tested against real Postgres/pgvector using a small
  deterministic `FakeEmbeddingProvider` (`tests/fakes.py`), injected via the
  same dependency-injection seam the real provider uses. This is standard
  test-double practice for external-service boundaries, not a product-facing
  fake — production code always defaults to the real provider.
- Actually downloading `all-MiniLM-L6-v2` and confirming real semantic
  similarity end-to-end needs to happen on your machine (or in CI with normal
  network access) — flagged here rather than asserted.

## Alternatives considered
- **OpenAI embeddings API**: `api.openai.com` is also not reachable from this
  sandbox, so it wouldn't have solved the verification problem either, and it
  reintroduces a per-token cost and external dependency for something that
  runs fine locally at this scale.
- **Ollama-served embedding model** (e.g. `nomic-embed-text`): reasonable
  alternative, consistent with ADR-004's Ollama default for LLM calls, but
  adds a runtime dependency on a separate Ollama server being up for
  ingestion specifically, versus an in-process library call. Worth
  revisiting if the LLM provider ends up being Ollama-hosted anyway and
  running one fewer moving part becomes attractive — not changing now
  without evidence, per §59.

## Consequences
- `requirements.txt` lists `sentence-transformers` as a real dependency;
  it's simply not installed in this sandbox's working venv (see
  `CLAUDE.md` §5) to preserve disk space here specifically.
- Embedding dimension (384) is fixed at the database schema level
  (`document_chunks.embedding`), so switching to a different-dimension model
  later requires a migration and re-embedding — this is treated as a
  deliberate, forcing constraint (see `app/models/document_chunk.py`), not
  a bug to design around.
