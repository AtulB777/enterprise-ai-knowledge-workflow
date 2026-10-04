import pytest

from evaluation.generation_metrics import (
    JudgeParseError,
    citation_precision,
    citation_recall,
    judge_faithfulness_and_relevance,
)
from tests.fakes import FakeLLMProvider


def test_citation_precision_all_cited_are_relevant() -> None:
    assert citation_precision({"a", "b"}, {"a", "b", "c"}) == 1.0


def test_citation_precision_some_cited_irrelevant() -> None:
    # Cited 2, only 1 was actually relevant -> 0.5
    assert citation_precision({"a", "x"}, {"a"}) == 0.5


def test_citation_precision_nothing_cited_is_zero() -> None:
    assert citation_precision(set(), {"a"}) == 0.0


def test_citation_recall_all_relevant_cited() -> None:
    assert citation_recall({"a", "b"}, {"a", "b"}) == 1.0


def test_citation_recall_missed_some_relevant() -> None:
    # Only 1 of 2 truly-relevant docs was cited -> 0.5
    assert citation_recall({"a"}, {"a", "b"}) == 0.5


def test_citation_recall_no_relevant_docs_is_vacuously_perfect() -> None:
    assert citation_recall({"a"}, set()) == 1.0


async def test_judge_parses_well_formed_response() -> None:
    fake_llm = FakeLLMProvider(response_text='{"faithfulness": 0.9, "relevance": 0.8}')

    scores = await judge_faithfulness_and_relevance(fake_llm, question="q", context="c", answer="a")

    assert scores == {"faithfulness": 0.9, "relevance": 0.8}


async def test_judge_clamps_out_of_range_scores() -> None:
    fake_llm = FakeLLMProvider(response_text='{"faithfulness": 1.5, "relevance": -0.3}')

    scores = await judge_faithfulness_and_relevance(fake_llm, question="q", context="c", answer="a")

    assert scores["faithfulness"] == 1.0
    assert scores["relevance"] == 0.0


async def test_judge_raises_clear_error_on_malformed_json() -> None:
    """A real production concern for any LLM-judge harness: the judge model
    itself can return unparseable output, and that must be a catchable,
    identifiable error — not a silent wrong score or a generic crash.
    """
    fake_llm = FakeLLMProvider(response_text="I think the answer looks pretty good overall.")

    with pytest.raises(JudgeParseError):
        await judge_faithfulness_and_relevance(fake_llm, question="q", context="c", answer="a")


async def test_judge_raises_clear_error_on_missing_fields() -> None:
    fake_llm = FakeLLMProvider(response_text='{"faithfulness": 0.9}')  # missing "relevance"

    with pytest.raises(JudgeParseError):
        await judge_faithfulness_and_relevance(fake_llm, question="q", context="c", answer="a")
