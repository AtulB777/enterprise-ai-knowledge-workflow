from app.core.metrics import LLM_LATENCY, MODEL_COST, TOKEN_USAGE
from app.services.llm.instrumented_provider import InstrumentedLLMProvider
from tests.fakes import FakeLLMProvider


def _counter_value(counter, **labels) -> float:
    for metric in counter.collect():
        for sample in metric.samples:
            if sample.name.endswith("_total") and sample.labels == labels:
                return sample.value
    return 0.0


def _histogram_count(histogram, **labels) -> float:
    for metric in histogram.collect():
        for sample in metric.samples:
            if sample.name.endswith("_count") and sample.labels == labels:
                return sample.value
    return 0.0


async def test_instrumented_provider_passes_through_the_real_response() -> None:
    inner = FakeLLMProvider(response_text="A real answer.")
    provider = InstrumentedLLMProvider(inner, provider_name="test-provider")

    from app.services.llm.provider import LLMMessage

    response = await provider.complete(
        system="sys", messages=[LLMMessage(role="user", content="q")], max_tokens=100
    )

    assert response.content == "A real answer."


async def test_instrumented_provider_records_token_usage() -> None:
    inner = FakeLLMProvider(response_text="answer")
    provider = InstrumentedLLMProvider(inner, provider_name="test-provider-tokens")

    from app.services.llm.provider import LLMMessage

    before_input = _counter_value(
        TOKEN_USAGE,
        provider="test-provider-tokens",
        model="fake-llm-test-only",
        token_type="input",
    )
    before_output = _counter_value(
        TOKEN_USAGE,
        provider="test-provider-tokens",
        model="fake-llm-test-only",
        token_type="output",
    )

    await provider.complete(
        system="sys", messages=[LLMMessage(role="user", content="q")], max_tokens=100
    )

    after_input = _counter_value(
        TOKEN_USAGE,
        provider="test-provider-tokens",
        model="fake-llm-test-only",
        token_type="input",
    )
    after_output = _counter_value(
        TOKEN_USAGE,
        provider="test-provider-tokens",
        model="fake-llm-test-only",
        token_type="output",
    )
    # FakeLLMProvider reports input_tokens=10, output_tokens=10 (see tests/fakes.py).
    assert after_input - before_input == 10
    assert after_output - before_output == 10


async def test_instrumented_provider_records_latency() -> None:
    inner = FakeLLMProvider(response_text="answer")
    provider = InstrumentedLLMProvider(inner, provider_name="test-provider-latency")

    from app.services.llm.provider import LLMMessage

    before_count = _histogram_count(
        LLM_LATENCY, provider="test-provider-latency", model="fake-llm-test-only"
    )

    await provider.complete(
        system="sys", messages=[LLMMessage(role="user", content="q")], max_tokens=100
    )

    after_count = _histogram_count(
        LLM_LATENCY, provider="test-provider-latency", model="fake-llm-test-only"
    )
    assert after_count - before_count == 1


async def test_instrumented_provider_records_zero_cost_for_unpriced_fake_model() -> None:
    """The fake model isn't in the pricing table, so cost should
    legitimately accumulate by zero — proving the cost path runs (doesn't
    error) without asserting a nonzero value that would require a priced
    real model.
    """
    inner = FakeLLMProvider(response_text="answer")
    provider = InstrumentedLLMProvider(inner, provider_name="test-provider-cost")

    from app.services.llm.provider import LLMMessage

    before = _counter_value(MODEL_COST, provider="test-provider-cost", model="fake-llm-test-only")

    await provider.complete(
        system="sys", messages=[LLMMessage(role="user", content="q")], max_tokens=100
    )

    after = _counter_value(MODEL_COST, provider="test-provider-cost", model="fake-llm-test-only")
    assert after - before == 0.0
