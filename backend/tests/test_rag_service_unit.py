"""Unit tests for the pure-function pieces of rag_service.py: query
normalization, context char-budget filtering, prompt structure, and citation
validation. These don't need a DB or LLM at all.
"""

import uuid
from unittest.mock import MagicMock

from app.models.document_chunk import DocumentChunk
from app.services.rag_service import (
    _build_user_content,
    _fit_to_char_budget,
    _normalize_query,
    _validate_citations,
)
from app.services.search_service import SearchResult


def _make_search_result(content: str, filename: str = "doc.txt") -> SearchResult:
    chunk = MagicMock(spec=DocumentChunk)
    chunk.id = uuid.uuid4()
    chunk.content = content
    return SearchResult(
        chunk=chunk,
        document_id=uuid.uuid4(),
        document_filename=filename,
        semantic_score=0.8,
        lexical_score=0.5,
        hybrid_score=0.7,
        rerank_score=None,
    )


def test_normalize_query_collapses_whitespace() -> None:
    assert _normalize_query("  what   is\n\nthe policy?  ") == "what is the policy?"


def test_fit_to_char_budget_includes_results_under_budget() -> None:
    results = [_make_search_result("a" * 100), _make_search_result("b" * 100)]
    fitted = _fit_to_char_budget(results, max_chars=1000)
    assert len(fitted) == 2


def test_fit_to_char_budget_stops_before_exceeding() -> None:
    results = [_make_search_result("a" * 100), _make_search_result("b" * 100)]
    fitted = _fit_to_char_budget(results, max_chars=150)
    assert len(fitted) == 1


def test_fit_to_char_budget_always_includes_at_least_one_result() -> None:
    """Even a single oversized chunk should be included rather than
    producing zero context — some context beats none.
    """
    results = [_make_search_result("x" * 5000)]
    fitted = _fit_to_char_budget(results, max_chars=100)
    assert len(fitted) == 1


def test_build_user_content_wraps_documents_and_question_separately() -> None:
    results = [_make_search_result("Revenue grew 12%.", filename="q3.txt")]

    content = _build_user_content("What was revenue growth?", results)

    assert "<retrieved_documents>" in content
    assert "</retrieved_documents>" in content
    assert "<user_question>" in content
    assert "What was revenue growth?" in content
    assert 'source="q3.txt"' in content
    assert "Revenue grew 12%." in content
    # The question must appear strictly after the documents close, proving
    # the two sections are genuinely separated, not just labeled.
    assert content.index("</retrieved_documents>") < content.index("<user_question>")


def test_build_user_content_numbers_documents_sequentially() -> None:
    results = [_make_search_result("First."), _make_search_result("Second.")]
    content = _build_user_content("q", results)
    assert 'document number="1"' in content
    assert 'document number="2"' in content


def test_validate_citations_keeps_valid_references() -> None:
    results = [_make_search_result("First doc."), _make_search_result("Second doc.")]
    validated = _validate_citations("The answer is here [1] and also here [2].", results)
    assert [c.citation_number for c in validated] == [1, 2]


def test_validate_citations_drops_out_of_range_numbers() -> None:
    """The core defense against fake citations (spec §18): a hallucinated
    [99] that doesn't correspond to any retrieved document must never
    become a persisted citation.
    """
    results = [_make_search_result("Only doc.")]
    validated = _validate_citations("See [1] and also [99] for details.", results)
    assert [c.citation_number for c in validated] == [1]


def test_validate_citations_deduplicates_repeated_references() -> None:
    results = [_make_search_result("Doc one.")]
    validated = _validate_citations("As stated [1], and again [1] later.", results)
    assert len(validated) == 1


def test_validate_citations_no_markers_returns_empty() -> None:
    results = [_make_search_result("Doc one.")]
    validated = _validate_citations("A confident answer with no citations at all.", results)
    assert validated == []


def test_validate_citations_uses_rerank_score_when_available() -> None:
    chunk = MagicMock(spec=DocumentChunk)
    chunk.id = uuid.uuid4()
    chunk.content = "content"
    result = SearchResult(
        chunk=chunk,
        document_id=uuid.uuid4(),
        document_filename="doc.txt",
        semantic_score=0.5,
        lexical_score=0.5,
        hybrid_score=0.5,
        rerank_score=0.95,
    )
    validated = _validate_citations("Answer [1].", [result])
    assert validated[0].relevance_score == 0.95


def test_validate_citations_falls_back_to_hybrid_score_without_rerank() -> None:
    result = _make_search_result("content")  # rerank_score=None by default
    validated = _validate_citations("Answer [1].", [result])
    assert validated[0].relevance_score == result.hybrid_score
