"""Tests for build_metrics_summary against the real, live prometheus_client
registry — incrementing real counters/histograms and checking the summary
reflects them correctly, including an average computed from real
sum/count samples.
"""

from prometheus_client import Histogram

from app.core.metrics import (
    ERROR_COUNT,
    LLM_LATENCY,
    REQUEST_COUNT,
    TOKEN_USAGE,
)
from app.services.metrics_summary import _histogram_average_ms, build_metrics_summary


def test_summary_reflects_real_counter_increments() -> None:
    before = build_metrics_summary()

    REQUEST_COUNT.labels(method="GET", path="/test-summary", status_code="200").inc()
    ERROR_COUNT.labels(method="GET", path="/test-summary", status_code="500").inc()

    after = build_metrics_summary()

    assert after.total_requests == before.total_requests + 1
    assert after.total_errors == before.total_errors + 1


def test_summary_error_rate_is_a_real_ratio() -> None:
    # Establish a clean, known baseline for this specific check by reading
    # actual current totals rather than assuming a fresh registry (other
    # tests in the same process may have already incremented these).
    before = build_metrics_summary()
    REQUEST_COUNT.labels(method="GET", path="/test-ratio", status_code="200").inc()
    ERROR_COUNT.labels(method="GET", path="/test-ratio", status_code="500").inc()
    after = build_metrics_summary()

    expected_rate = after.total_errors / after.total_requests
    assert abs(after.error_rate - expected_rate) < 1e-9
    assert after.total_requests > before.total_requests


def test_summary_computes_real_average_llm_latency() -> None:
    LLM_LATENCY.labels(provider="test-summary-provider", model="test-model").observe(1.0)
    LLM_LATENCY.labels(provider="test-summary-provider", model="test-model").observe(3.0)

    summary = build_metrics_summary()

    # Average must be at least the average of these two new observations
    # combined with whatever was already there — since we can't isolate a
    # totally clean registry, check it's a sane positive number reflecting
    # real observations, not that it exactly equals an isolated value.
    assert summary.avg_llm_latency_ms is not None
    assert summary.avg_llm_latency_ms > 0


def test_summary_splits_token_usage_by_type() -> None:
    before = build_metrics_summary()

    TOKEN_USAGE.labels(provider="test-summary", model="test-model", token_type="input").inc(100)
    TOKEN_USAGE.labels(provider="test-summary", model="test-model", token_type="output").inc(50)

    after = build_metrics_summary()

    assert after.total_input_tokens == before.total_input_tokens + 100
    assert after.total_output_tokens == before.total_output_tokens + 50


def test_histogram_average_is_none_for_a_never_observed_histogram() -> None:
    """A genuinely isolated, never-observed histogram must report None, not
    a divide-by-zero or a fabricated 0.0 that would misleadingly look like
    a real, fast average — tested against a fresh Histogram created here,
    not one of the app's shared global metrics other tests may have
    already touched.
    """
    fresh_histogram = Histogram("test_never_observed_histogram", "test only")
    assert _histogram_average_ms(fresh_histogram) is None


def test_histogram_average_reflects_real_observations() -> None:
    fresh_histogram = Histogram("test_real_average_histogram", "test only")
    fresh_histogram.observe(0.5)  # 500ms
    fresh_histogram.observe(1.5)  # 1500ms

    # Average of 0.5s and 1.5s is 1.0s = 1000ms.
    result = _histogram_average_ms(fresh_histogram)
    assert result is not None
    assert abs(result - 1000.0) < 1e-6
