"""Ollama-backed LLM provider — real implementation (see ADR-010).

Plain HTTP calls to Ollama's local `/api/chat` endpoint; no SDK needed.
Not live-testable in this sandbox (no Ollama server running here — same
class of constraint as the embedding/reranking models, just a different
missing piece), but this is real, complete code, not a stub.
"""

import httpx

from app.core.config import get_settings
from app.services.llm.provider import LLMMessage, LLMResponse


class OllamaProvider:
    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self._model = model or settings.ollama_model

    async def complete(
        self, *, system: str, messages: list[LLMMessage], max_tokens: int
    ) -> LLMResponse:
        payload = {
            "model": self._model,
            "messages": [{"role": "system", "content": system}]
            + [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(f"{self._base_url}/api/chat", json=payload)
            response.raise_for_status()
            body = response.json()

        return LLMResponse(
            content=body["message"]["content"],
            model=body.get("model", self._model),
            input_tokens=body.get("prompt_eval_count"),
            output_tokens=body.get("eval_count"),
        )
