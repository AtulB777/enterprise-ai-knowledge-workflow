"""Test doubles for external-service boundaries.

`FakeEmbeddingProvider` is used ONLY in tests, injected via the same
dependency-injection seam (`process_document`'s `embedding_provider` param)
that production code uses for the real `SentenceTransformersEmbeddingProvider`
— see ADR-008 for why the real model can't be exercised live in this sandbox,
and why this is standard test-double practice rather than a product-facing
fake.
"""

import hashlib
import math

from app.services.llm.provider import LLMMessage, LLMResponse


class FakeEmbeddingProvider:
    """Deterministic word-hashing embedding: each word hashes into one of
    `dimension` buckets (sign also hashed), vector L2-normalized. Real,
    simple algorithm — texts sharing more words land closer together in
    cosine distance — enough to meaningfully test "most similar chunk"
    retrieval against real pgvector, without claiming any real semantic
    quality. Never used outside tests/.
    """

    def __init__(self, dimension: int = 384) -> None:
        self._dimension = dimension

    @property
    def model_name(self) -> str:
        return "fake-hashing-embedding-test-only"

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self._dimension
        words = text.lower().split() or [""]
        for word in words:
            digest = hashlib.sha256(word.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % self._dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]


class FakeReranker:
    """Deterministic lexical-overlap reranker: score = fraction of query
    words that appear in the document, real (if simple) algorithm, test-only
    — see ADR-009 for why the real cross-encoder can't run in this sandbox.
    """

    async def rerank(self, *, query: str, documents: list[str]) -> list[float]:
        query_words = set(query.lower().split())
        if not query_words:
            return [0.0] * len(documents)
        scores = []
        for doc in documents:
            doc_words = set(doc.lower().split())
            overlap = len(query_words & doc_words)
            scores.append(overlap / len(query_words))
        return scores


class FakeLLMProvider:
    """Deterministic LLM stand-in for tests — see ADR-010 for why real
    completions can't run in this sandbox (no API key available; the
    Anthropic API itself is reachable, unlike the blocked embedding/
    reranking model hosts).

    Default behavior: counts how many <document> blocks were provided in the
    prompt and cites all of them by number, so tests can exercise the real
    citation-extraction/validation logic end-to-end. Pass `response_text` to
    return fixed output instead — e.g. to test that an out-of-range citation
    number like [99] gets correctly dropped by validation.
    """

    def __init__(self, response_text: str | None = None) -> None:
        self._response_text = response_text

    async def complete(
        self, *, system: str, messages: list[LLMMessage], max_tokens: int
    ) -> LLMResponse:
        if self._response_text is not None:
            content = self._response_text
        else:
            user_content = messages[-1].content if messages else ""
            document_count = user_content.count("<document ")
            if document_count == 0:
                content = "I don't have enough information to answer that."
            else:
                citation_markers = " ".join(f"[{i + 1}]" for i in range(document_count))
                content = f"Based on the provided documents, here is the answer. {citation_markers}"

        return LLMResponse(
            content=content, model="fake-llm-test-only", input_tokens=10, output_tokens=10
        )


class SequencedLLMProvider:
    """Returns a different fixed response on each successive call, in order
    — needed for testing the agent loop (ADR-012), which calls the planner
    multiple times across one run and expects a different JSON action each
    time (e.g. a tool_call, then a final_answer). FakeLLMProvider's single
    fixed response_text can't express that. Raises if called more times than
    responses were provided, rather than silently repeating the last one —
    an agent test that needs more planner calls than expected should fail
    loudly, not pass on a misleading response.
    """

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self._call_count = 0

    async def complete(
        self, *, system: str, messages: list[LLMMessage], max_tokens: int
    ) -> LLMResponse:
        if self._call_count >= len(self._responses):
            raise AssertionError(
                f"SequencedLLMProvider called {self._call_count + 1} times but only "
                f"{len(self._responses)} responses were configured."
            )
        content = self._responses[self._call_count]
        self._call_count += 1
        return LLMResponse(
            content=content, model="fake-llm-test-only", input_tokens=10, output_tokens=10
        )
