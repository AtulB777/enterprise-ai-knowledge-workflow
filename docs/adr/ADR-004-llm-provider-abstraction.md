# ADR-004: LLM Provider Abstraction

**Status:** Accepted

## Context
Must not depend exclusively on one proprietary LLM. Must support local inference
(constrained hardware: 8GB RAM, RTX 3050 6GB VRAM) and cloud APIs, switchable without
touching business logic.

## Decision
An `LLMProvider` protocol/interface with a uniform method surface (`complete`, `stream`,
`embed` where applicable) and concrete implementations:
- `OllamaProvider` (default for local dev — runs quantized models within the VRAM budget)
- `OpenAIProvider`
- `AnthropicProvider`
- `GeminiProvider`

Selected via configuration (`LLM_PROVIDER` env var + per-request override for the model
router, see spec section 30), never hard-coded in RAG/agent code.

## Reasoning
- The 6GB VRAM constraint rules out running a large local model reliably — Ollama with a
  small quantized model (e.g. a ~3-8B parameter model) is realistic; the abstraction lets
  the same code path call a stronger cloud model when quality matters more than privacy/cost.
- Isolates all provider-specific request/response shaping (function calling formats,
  streaming protocols, token counting) behind one interface, so the RAG pipeline and agent
  system are provider-agnostic.

## Trade-offs
- Slight overhead in maintaining a common interface across providers with different
  capabilities (e.g. not all models support the same function-calling schema) — handled by
  each provider adapter normalizing to a common internal tool-call representation.

## Consequences
- Adding a new provider (or a new local runtime) is additive, not a refactor.
- Model routing (section 30) and cost tracking (section 31) both key off the provider/model
  identifiers this abstraction already records per request.
