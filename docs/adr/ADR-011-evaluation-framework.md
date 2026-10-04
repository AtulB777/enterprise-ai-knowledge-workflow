# ADR-011: Evaluation Framework

**Status:** Accepted

## Context
Spec §27/§28 require a dedicated evaluation module measuring RAG quality
(retrieval recall/precision@K/MRR/NDCG, context/answer relevance,
faithfulness, citation correctness), system performance (latency, tokens,
cost, error rate), and agent quality — plus a reproducible golden dataset
and a `python -m evaluation.run` command producing a report, with
current-vs-baseline regression detection.

## Scope relative to what exists so far
Agent-quality metrics (task success rate, tool selection accuracy, etc.)
are explicitly NOT implemented in this phase — there is no agent system yet
(that's Phase 9). Building evaluation metrics for a system that doesn't
exist would be speculative code with nothing real to measure. This phase
covers RAG retrieval quality, RAG generation quality, and system
performance — the parts of §27 that have a real pipeline (Phases 4-7) to
evaluate. Agent evaluation is added in Phase 9 once there's something to
evaluate, extending this same framework rather than replacing it.

## Decision
`backend/evaluation/` — a package separate from `app/`, matching the
spec's literal `python -m evaluation.run` invocation:
- `golden_dataset.py` — a small, versioned, reproducible set of synthetic
  documents and queries with hand-labeled relevant-document ground truth.
- `retrieval_metrics.py` — recall@K, precision@K, MRR, NDCG. Pure functions,
  zero external dependencies, correctness verified against textbook
  hand-computed examples.
- `generation_metrics.py` — citation correctness (deterministic: precision/
  recall of cited documents against ground-truth relevant documents) and
  an LLM-judge implementation for faithfulness and answer relevance.
- `runner.py` / `run.py` — orchestrates a run against real Postgres/pgvector
  using whichever providers `app/services/*/factory.py` resolve (the same
  DI seam as everywhere else — injectable for tests, real by default),
  persists results, and prints/compares a report.

## LLM-judge, and the same honest constraint as ADR-010
Faithfulness and answer relevance are inherently semantic judgments —
citation correctness can be computed by set comparison alone, but "is this
answer actually supported by the retrieved context" cannot be determined by
a formula. The standard approach, and the one used here, is LLM-as-judge:
prompt a model to score the (question, context, answer) triple and parse a
structured score back out.

This has the identical constraint as ADR-010: no API key is available in
this sandbox to run a real judge call. Verification here follows the same
pattern already established:
- The judge prompt construction and response parsing (including graceful
  handling of a malformed/unparseable judge response — a real production
  concern, not just a happy-path assumption) are unit-tested with a
  `FakeLLMProvider` returning both well-formed and malformed judge output.
- The full evaluation run — golden dataset ingestion through the real
  pipeline, retrieval metrics, citation correctness, DB persistence, and
  baseline comparison — is proven end-to-end against real Postgres/pgvector
  with fake embedding/reranking/LLM providers injected, same as every
  pipeline test since Phase 5.
- Genuinely meaningful faithfulness/relevance *scores* (not just "the code
  runs") require a real judge model — that verification needs to happen on
  a machine with API access, exactly like real RAG answer quality in
  Phase 7.

## Regression detection (spec §28)
Each run is tagged with the golden dataset's version string and persisted
(`evaluation_runs`, `evaluation_results` — spec §35's schema, added now).
`python -m evaluation.run` automatically compares aggregate metrics against
the most recent prior run for the same dataset version, if one exists, and
flags any metric that dropped by more than a configurable threshold
(default 5 percentage points) as a regression — printed clearly, not just
silently logged, and the process exits non-zero so CI can fail on it.

## Consequences
- Evaluation reuses real application services (upload, ingestion, search,
  RAG) rather than reimplementing retrieval/generation logic — a change to
  those services is automatically reflected in evaluation runs, so the
  harness can't silently drift from what production code actually does.
- The golden dataset lives in version control as plain data (not generated
  at runtime), so "reproducible" means what it says — the same input every
  run, changes to it are a reviewable diff.
