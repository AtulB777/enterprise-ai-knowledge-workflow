"""Standard information-retrieval metrics (spec §27): recall@K, precision@K,
MRR, NDCG. Pure functions — no DB, no LLM, no network — operating on ordered
lists of retrieved IDs against a set of known-relevant IDs. Correctness is
verified in tests against hand-computed textbook examples, not just "the
code runs."
"""

import math


def recall_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """Fraction of all relevant items that appear in the top K retrieved.
    Vacuously 1.0 if there are no relevant items at all — there's nothing to
    miss, so recall can't meaningfully be penalized.
    """
    if not relevant_ids:
        return 1.0
    top_k = set(retrieved_ids[:k])
    return len(top_k & relevant_ids) / len(relevant_ids)


def precision_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """Fraction of the top K retrieved items that are actually relevant."""
    top_k = retrieved_ids[:k]
    if not top_k:
        return 0.0
    hits = len(set(top_k) & relevant_ids)
    return hits / len(top_k)


def mean_reciprocal_rank(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
    """1/rank of the first relevant item found, 0.0 if none appear at all.
    ("Mean" refers to averaging this across many queries — that averaging
    happens at the evaluation-run level, not inside this per-query function.)
    """
    for rank, doc_id in enumerate(retrieved_ids, start=1):
        if doc_id in relevant_ids:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """Normalized Discounted Cumulative Gain with binary relevance (each
    retrieved item is either relevant or not — no graded relevance scores
    in the golden dataset, so DCG reduces to 1/log2(rank+1) per hit).
    """
    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, doc_id in enumerate(retrieved_ids[:k], start=1)
        if doc_id in relevant_ids
    )
    ideal_hit_count = min(len(relevant_ids), k)
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hit_count + 1))
    if idcg == 0:
        return 0.0
    return dcg / idcg
