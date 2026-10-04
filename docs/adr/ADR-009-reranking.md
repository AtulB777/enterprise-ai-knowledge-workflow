# ADR-009: Reranking

**Status:** Accepted

## Context
Spec §16 and CLAUDE.md's Phase 2 stack decision call for an optional
cross-encoder reranking stage between hybrid retrieval and final context
assembly: `Retriever -> Top N -> Reranker -> Top K`.

## Decision
`Reranker` protocol (`app/services/reranking/reranker.py`) with
`CrossEncoderReranker` (`cross-encoder/ms-marco-MiniLM-L-6-v2`) as the
default real implementation, following the exact same pattern ADR-008
established for embeddings — because it's the same underlying constraint.

## Same sandbox constraint as ADR-008, same resolution
`sentence-transformers.CrossEncoder` needs the same Hugging Face model
download this sandbox's egress proxy blocks, and pulls in the same PyTorch
dependency that exhausted this sandbox's disk budget in Phase 5. Rather than
inventing a different workaround, this ADR deliberately reuses ADR-008's
already-established, already-justified pattern:
- The import is lazy (inside the method, not module top level), so this
  module can be imported and its own logic unit-tested without the real
  package installed.
- `CrossEncoderReranker`'s own wrapper logic (batching query-document pairs,
  score ordering, async offload via `asyncio.to_thread`) is unit-tested by
  mocking the `sentence_transformers` import boundary — same technique as
  `tests/test_sentence_transformers_provider.py`.
- The full hybrid-search-then-rerank pipeline is tested against real
  Postgres/pgvector using a small deterministic `FakeReranker`
  (`tests/fakes.py`) — real algorithm (lexical overlap scoring), clearly
  tests-only, injected via the same DI seam the real reranker uses.
- Actually downloading `ms-marco-MiniLM-L-6-v2` and confirming reranking
  quality end-to-end needs to happen on your machine, same as ADR-008.

## Reasoning for keeping reranking optional (not always-on)
Per spec §16, reranking is explicitly optional. Implemented as a request-level
toggle (`rerank: bool = True` on the search request) rather than a hard
requirement, so:
- Search still works completely (hybrid retrieval alone) in environments
  where the reranker model isn't available yet — this sandbox included.
- Callers that only need fast approximate results (e.g. an agent doing many
  quick lookups) can skip the extra latency of a second model pass.

## Alternatives considered
- **No reranking, hybrid score only**: simpler, but skips a real quality
  improvement the spec explicitly calls for, and the fusion of two
  differently-scaled signals (cosine similarity, ts_rank) benefits from a
  reranking pass that judges (query, chunk) pairs directly rather than
  combining two independent estimates.
- **LLM-based reranking** (ask the LLM to score relevance): more expensive
  per query, adds a dependency on the LLM provider (not yet built — that's
  Phase 7) being available for every search call, not just chat. A dedicated
  small cross-encoder is faster and purpose-built for this.

## Consequences
- `requirements.txt` lists `sentence-transformers` already (ADR-008); no new
  production dependency — `CrossEncoder` is a class within the same package.
- Reranker model/version isn't currently recorded per-search-result the way
  `embedding_model` is recorded per-chunk — acceptable for now since rerank
  scores aren't persisted (computed fresh per query), only chunk embeddings
  are; revisit if search analytics (Phase 32) end up needing it.
