"""Tests for SentenceTransformersEmbeddingProvider's own logic (batching,
dimension validation, async offload) — mocking the `sentence_transformers`
import boundary rather than requiring the real (heavy, network-dependent)
package. See ADR-008 for why this sandbox can't install/run the real thing,
and why mocking a third-party library boundary here is standard practice,
not a product-facing fake.
"""

import sys
import types
from unittest.mock import MagicMock

import pytest

from app.services.embeddings.sentence_transformers_provider import (
    EmbeddingDimensionMismatchError,
    SentenceTransformersEmbeddingProvider,
)


def _install_fake_sentence_transformers_module(*, output_dimension: int) -> MagicMock:
    """Installs a fake `sentence_transformers` module into sys.modules so the
    provider's lazy `from sentence_transformers import SentenceTransformer`
    resolves to our mock instead of attempting a real import.
    """
    fake_module = types.ModuleType("sentence_transformers")
    mock_model_instance = MagicMock()

    class _FakeNumpyArray:
        def __init__(self, data: list[list[float]]) -> None:
            self._data = data

        def tolist(self) -> list[list[float]]:
            return self._data

    def _fake_encode(texts: list[str], **kwargs: object) -> _FakeNumpyArray:
        return _FakeNumpyArray([[0.1] * output_dimension for _ in texts])

    mock_model_instance.encode.side_effect = _fake_encode
    mock_constructor = MagicMock(return_value=mock_model_instance)
    fake_module.SentenceTransformer = mock_constructor  # type: ignore[attr-defined]
    sys.modules["sentence_transformers"] = fake_module
    return mock_constructor


@pytest.fixture(autouse=True)
def _cleanup_fake_module():
    yield
    sys.modules.pop("sentence_transformers", None)


async def test_embed_returns_one_vector_per_input_text() -> None:
    _install_fake_sentence_transformers_module(output_dimension=384)
    provider = SentenceTransformersEmbeddingProvider(
        model_name="fake-model", expected_dimension=384
    )

    result = await provider.embed(["first text", "second text", "third text"])

    assert len(result) == 3
    assert all(len(vec) == 384 for vec in result)


async def test_embed_empty_list_returns_empty_without_loading_model() -> None:
    mock_constructor = _install_fake_sentence_transformers_module(output_dimension=384)
    provider = SentenceTransformersEmbeddingProvider(
        model_name="fake-model", expected_dimension=384
    )

    result = await provider.embed([])

    assert result == []
    mock_constructor.assert_not_called()


async def test_model_is_loaded_lazily_only_once() -> None:
    mock_constructor = _install_fake_sentence_transformers_module(output_dimension=384)
    provider = SentenceTransformersEmbeddingProvider(
        model_name="fake-model", expected_dimension=384
    )

    assert mock_constructor.call_count == 0
    await provider.embed(["one"])
    await provider.embed(["two"])

    assert mock_constructor.call_count == 1


async def test_dimension_mismatch_raises_clear_error() -> None:
    _install_fake_sentence_transformers_module(output_dimension=128)
    provider = SentenceTransformersEmbeddingProvider(
        model_name="wrong-dimension-model", expected_dimension=384
    )

    with pytest.raises(EmbeddingDimensionMismatchError, match="128"):
        await provider.embed(["some text"])


def test_provider_reports_configured_model_name_and_dimension() -> None:
    provider = SentenceTransformersEmbeddingProvider(model_name="my-model", expected_dimension=256)

    assert provider.model_name == "my-model"
    assert provider.dimension == 256


def test_provider_defaults_come_from_settings() -> None:
    provider = SentenceTransformersEmbeddingProvider()

    assert provider.model_name == "sentence-transformers/all-MiniLM-L6-v2"
    assert provider.dimension == 384
