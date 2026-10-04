"""Metrics instrumentation for any LLMProvider (spec §29's LLM_LATENCY,
TOKEN_USAGE, MODEL_COST). A decorator, not duplicated code in
AnthropicProvider/OllamaProvider — applied once, at the factory, to
whichever concrete provider is actually configured, so a future third
provider gets instrumentation for free rather than needing to remember to
add it.
"""

import time

from app.core.metrics import LLM_LATENCY, MODEL_COST, TOKEN_USAGE
from app.core.pricing import estimate_cost_usd
from app.services.llm.provider import LLMMessage, LLMProvider, LLMResponse


class InstrumentedLLMProvider:
    def __init__(self, inner: LLMProvider, *, provider_name: str) -> None:
        self._inner = inner
        self._provider_name = provider_name

    async def complete(
        self, *, system: str, messages: list[LLMMessage], max_tokens: int
    ) -> LLMResponse:
        start = time.monotonic()
        response = await self._inner.complete(
            system=system, messages=messages, max_tokens=max_tokens
        )
        elapsed_seconds = time.monotonic() - start

        LLM_LATENCY.labels(provider=self._provider_name, model=response.model).observe(
            elapsed_seconds
        )
        if response.input_tokens is not None:
            TOKEN_USAGE.labels(
                provider=self._provider_name, model=response.model, token_type="input"
            ).inc(response.input_tokens)
        if response.output_tokens is not None:
            TOKEN_USAGE.labels(
                provider=self._provider_name, model=response.model, token_type="output"
            ).inc(response.output_tokens)
        if response.input_tokens is not None and response.output_tokens is not None:
            cost = estimate_cost_usd(
                model=response.model,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
            )
            MODEL_COST.labels(provider=self._provider_name, model=response.model).inc(cost)

        return response
