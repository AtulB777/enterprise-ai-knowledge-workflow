"""Anthropic-backed LLM provider — real implementation (see ADR-010).

Unlike the embedding/reranking providers, this doesn't need a lazy import:
the `anthropic` SDK is lightweight (no PyTorch), installs cleanly everywhere,
so importing it at module level costs nothing meaningful.
"""

from anthropic import AsyncAnthropic

from app.core.config import get_settings
from app.services.llm.provider import LLMMessage, LLMResponse


class AnthropicProvider:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        resolved_key = api_key or settings.anthropic_api_key
        if not resolved_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not configured. Set it in .env before "
                "using the Anthropic LLM provider."
            )
        self._client = AsyncAnthropic(api_key=resolved_key)
        self._model = model or settings.anthropic_model

    async def complete(
        self, *, system: str, messages: list[LLMMessage], max_tokens: int
    ) -> LLMResponse:
        response = await self._client.messages.create(
            model=self._model,
            system=system,
            max_tokens=max_tokens,
            messages=[{"role": m.role, "content": m.content} for m in messages],
        )
        # Anthropic responses are a list of content blocks; RAG completions
        # are plain text, so concatenate any text blocks (there is normally
        # exactly one, since no tool use is requested here).
        text = "".join(block.text for block in response.content if block.type == "text")
        return LLMResponse(
            content=text,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
