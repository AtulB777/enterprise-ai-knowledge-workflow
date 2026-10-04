"""Retrieval metrics verified against hand-computed values, not just
"the code runs" — these are standard IR formulas with well-known behavior
on small examples.
"""

from evaluation.retrieval_metrics import (
    mean_reciprocal_rank,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)


def test_recall_at_k_all_relevant_found() -> None:
    retrieved = ["a", "b", "c"]
    relevant = {"a", "c"}
    assert recall_at_k(retrieved, relevant, k=3) == 1.0


def test_recall_at_k_partial() -> None:
    retrieved = ["a", "x", "y"]
    relevant = {"a", "b"}
    # Only "a" of the two relevant docs was retrieved -> 1/2
    assert recall_at_k(retrieved, relevant, k=3) == 0.5


def test_recall_at_k_respects_k_cutoff() -> None:
    retrieved = ["x", "y", "a"]  # relevant doc is at rank 3
    relevant = {"a"}
    assert recall_at_k(retrieved, relevant, k=2) == 0.0
    assert recall_at_k(retrieved, relevant, k=3) == 1.0


def test_recall_at_k_no_relevant_docs_is_vacuously_perfect() -> None:
    assert recall_at_k(["a", "b"], set(), k=5) == 1.0


def test_precision_at_k_basic() -> None:
    retrieved = ["a", "b", "c", "d"]
    relevant = {"a", "c"}
    # top 4: 2 of 4 are relevant -> 0.5
    assert precision_at_k(retrieved, relevant, k=4) == 0.5


def test_precision_at_k_respects_k_cutoff() -> None:
    retrieved = ["a", "x", "y", "z"]
    relevant = {"a"}
    # top 1: 1/1 relevant
    assert precision_at_k(retrieved, relevant, k=1) == 1.0
    # top 4: 1/4 relevant
    assert precision_at_k(retrieved, relevant, k=4) == 0.25


def test_precision_at_k_empty_retrieval() -> None:
    assert precision_at_k([], {"a"}, k=5) == 0.0


def test_mrr_first_relevant_at_rank_one() -> None:
    assert mean_reciprocal_rank(["a", "b"], {"a"}) == 1.0


def test_mrr_first_relevant_at_rank_three() -> None:
    assert mean_reciprocal_rank(["x", "y", "a"], {"a"}) == 1 / 3


def test_mrr_no_relevant_found() -> None:
    assert mean_reciprocal_rank(["x", "y", "z"], {"a"}) == 0.0


def test_ndcg_perfect_ranking_is_one() -> None:
    # Two relevant docs, both ranked first -> ideal ranking -> NDCG = 1.0
    retrieved = ["a", "b", "x", "y"]
    relevant = {"a", "b"}
    assert ndcg_at_k(retrieved, relevant, k=4) == 1.0


def test_ndcg_worse_ranking_scores_lower_than_perfect() -> None:
    perfect = ndcg_at_k(["a", "b", "x", "y"], {"a", "b"}, k=4)
    worse = ndcg_at_k(["x", "y", "a", "b"], {"a", "b"}, k=4)
    assert worse < perfect


def test_ndcg_no_relevant_docs_is_zero() -> None:
    assert ndcg_at_k(["a", "b"], set(), k=5) == 0.0


def test_ndcg_no_hits_is_zero() -> None:
    assert ndcg_at_k(["x", "y"], {"a"}, k=5) == 0.0


def test_ndcg_hand_computed_example() -> None:
    # Textbook example: relevant doc at rank 2 out of 1 possible relevant doc.
    # DCG = 1/log2(3) ≈ 0.6309; ideal DCG (relevant at rank 1) = 1/log2(2) = 1.0
    # NDCG = 0.6309 / 1.0 ≈ 0.6309
    result = ndcg_at_k(["x", "a"], {"a"}, k=2)
    assert abs(result - 0.6309) < 0.001
