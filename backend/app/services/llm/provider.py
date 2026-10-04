"""LLM provider abstraction (ADR-004, implemented in ADR-010).

Business logic (the RAG pipeline) depends only on this Protocol, never on a
concrete provider — same pattern as EmbeddingProvider/Reranker.
"""

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class LLMMessage:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class LLMResponse:
    content: str
    model: str
    # Token counts are Optional because not every provider necessarily
    # reports them the same way — captured now since it's essentially free
    # and directly feeds cost tracking (spec §31) in a later phase.
    input_tokens: int | None
    output_tokens: int | None


class LLMProvider(Protocol):
    async def complete(
        self, *, system: str, messages: list[LLMMessage], max_tokens: int
    ) -> LLMResponse:
        """Generates a single completion. `messages` is the full turn
        history for this request (RAG here always sends exactly one user
        message per call — multi-turn context is handled by the caller
        assembling conversation history into `messages`, not by this
        provider maintaining state).
        """
        ...
