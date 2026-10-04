from app.core.pricing import estimate_cost_usd


def test_estimate_cost_for_known_model() -> None:
    # claude-sonnet-4-5: $3/million input, $15/million output.
    # 1,000,000 input tokens -> $3.00; 100,000 output tokens -> $1.50
    cost = estimate_cost_usd(
        model="claude-sonnet-4-5-20250929", input_tokens=1_000_000, output_tokens=100_000
    )
    assert abs(cost - 4.50) < 1e-9


def test_estimate_cost_zero_tokens_is_zero() -> None:
    cost = estimate_cost_usd(model="claude-sonnet-4-5-20250929", input_tokens=0, output_tokens=0)
    assert cost == 0.0


def test_estimate_cost_unknown_model_is_zero_not_an_error() -> None:
    """An Ollama-hosted (local, free) or otherwise unrecognized model must
    not raise — it just doesn't contribute anything to the cost estimate.
    """
    cost = estimate_cost_usd(model="llama3.1:8b", input_tokens=50_000, output_tokens=10_000)
    assert cost == 0.0
