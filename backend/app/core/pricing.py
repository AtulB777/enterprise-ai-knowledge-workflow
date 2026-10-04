"""Approximate LLM cost estimation (spec §29 MODEL_COST metric, §31 cost
tracking; closes a gap ADR-011 planned but never actually wired up in
Phase 8 — see ADR-014 decision 4).

Pricing changes over time and varies by provider. This table is a
reasonable default for cost *estimation*, not a live-fetched or
contractually-guaranteed source — verify against each provider's current
published pricing (e.g. anthropic.com/pricing) before relying on this for
real billing/budget decisions, same principle ADR-011 already established
for evaluation cost estimates.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPricing:
    input_cost_per_million_tokens: float
    output_cost_per_million_tokens: float


_PRICING_TABLE: dict[str, ModelPricing] = {
    "claude-sonnet-4-5-20250929": ModelPricing(
        input_cost_per_million_tokens=3.0, output_cost_per_million_tokens=15.0
    ),
}

# Anything not in the table above (including every Ollama-hosted model,
# which runs locally with no per-token API cost) is treated as free rather
# than raising — an unrecognized/local model shouldn't break cost
# *estimation*, it just contributes nothing to the estimate.
_ZERO_COST = ModelPricing(input_cost_per_million_tokens=0.0, output_cost_per_million_tokens=0.0)


def estimate_cost_usd(*, model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = _PRICING_TABLE.get(model, _ZERO_COST)
    return (input_tokens / 1_000_000) * pricing.input_cost_per_million_tokens + (
        output_tokens / 1_000_000
    ) * pricing.output_cost_per_million_tokens
