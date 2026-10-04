"""Tests for CrossEncoderReranker's own logic (pairing, batching, async
offload) — mocking the `sentence_transformers` import boundary, same
technique as test_sentence_transformers_provider.py. See ADR-009.
"""

import sys
import types
from unittest.mock import MagicMock

import pytest

from app.services.reranking.cross_encoder_reranker import CrossEncoderReranker


def _install_fake_cross_encoder_module(*, scores: list[float]) -> MagicMock:
    fake_module = types.ModuleType("sentence_transformers")
    mock_model_instance = MagicMock()
    mock_model_instance.predict.return_value = scores
    mock_constructor = MagicMock(return_value=mock_model_instance)
    fake_module.CrossEncoder = mock_constructor  # type: ignore[attr-defined]
    sys.modules["sentence_transformers"] = fake_module
    return mock_constructor


@pytest.fixture(autouse=True)
def _cleanup_fake_module():
    yield
    sys.modules.pop("sentence_transformers", None)


async def test_rerank_returns_one_score_per_document_in_order() -> None:
    _install_fake_cross_encoder_module(scores=[0.9, 0.1, 0.5])
    reranker = CrossEncoderReranker(model_name="fake-reranker-model")

    scores = await reranker.rerank(query="test query", documents=["doc a", "doc b", "doc c"])

    assert scores == [0.9, 0.1, 0.5]


async def test_rerank_pairs_query_with_each_document() -> None:
    mock_constructor = _install_fake_cross_encoder_module(scores=[0.5, 0.5])
    reranker = CrossEncoderReranker(model_name="fake-reranker-model")

    await reranker.rerank(query="my query", documents=["first doc", "second doc"])

    predict_call_args = mock_constructor.return_value.predict.call_args[0][0]
    assert predict_call_args == [["my query", "first doc"], ["my query", "second doc"]]


async def test_rerank_empty_documents_returns_empty_without_loading_model() -> None:
    mock_constructor = _install_fake_cross_encoder_module(scores=[])
    reranker = CrossEncoderReranker(model_name="fake-reranker-model")

    result = await reranker.rerank(query="anything", documents=[])

    assert result == []
    mock_constructor.assert_not_called()


async def test_model_is_loaded_lazily_only_once() -> None:
    mock_constructor = _install_fake_cross_encoder_module(scores=[0.1])
    reranker = CrossEncoderReranker(model_name="fake-reranker-model")

    await reranker.rerank(query="q", documents=["d1"])
    await reranker.rerank(query="q", documents=["d1"])

    assert mock_constructor.call_count == 1


def test_reranker_defaults_come_from_settings() -> None:
    reranker = CrossEncoderReranker()
    assert reranker._model_name == "cross-encoder/ms-marco-MiniLM-L-6-v2"
