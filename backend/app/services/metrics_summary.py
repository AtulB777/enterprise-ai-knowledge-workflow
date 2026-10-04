"""Admin metrics snapshot (spec §29/§32, ADR-018 decision 3).

Reads the same in-process `prometheus_client` registry `/metrics` already
exposes via its own `.collect()` API — this is a curated JSON view of the
exact same live counters, not a second, parallel counting mechanism that
could drift from what `/metrics` reports.

A snapshot, not a time series: these values are cumulative since this
server process started, nothing more. See ADR-018 decision 3 for why a
real historical dashboard needs actual Prometheus+Grafana infrastructure
this project doesn't run, and why this deliberately doesn't pretend to be
that.
"""

from dataclasses import dataclass

from prometheus_client.metrics import MetricWrapperBase


@dataclass(frozen=True)
class MetricsSummary:
    total_requests: int
    total_errors: int
    error_rate: float
    avg_request_latency_ms: float | None
    total_input_tokens: int
    total_output_tokens: int
    total_estimated_cost_usd: float
    avg_retrieval_latency_ms: float | None
    avg_llm_latency_ms: float | None
    total_agent_steps: int
    total_rate_limit_rejections: int


def _sum_by_suffix(metric: MetricWrapperBase, suffix: str) -> float:
    total = 0.0
    for family in metric.collect():
        for sample in family.samples:
            if sample.name.endswith(suffix):
                total += sample.value
    return total


def _histogram_average_ms(metric: MetricWrapperBase) -> float | None:
    total_sum = _sum_by_suffix(metric, "_sum")
    total_count = _sum_by_suffix(metric, "_count")
    if total_count == 0:
        return None
    return (total_sum / total_count) * 1000


def build_metrics_summary() -> MetricsSummary:
    # Imported here, not at module level: keeps this module's only
    # dependency on the metric *objects* explicit at the call site, since
    # app.core.metrics is otherwise only ever imported for instrumentation,
    # not for reading values back out.
    from app.core.metrics import (
        AGENT_STEPS,
        ERROR_COUNT,
        LLM_LATENCY,
        MODEL_COST,
        RATE_LIMIT_EXCEEDED,
        REQUEST_COUNT,
        REQUEST_LATENCY,
        RETRIEVAL_LATENCY,
        TOKEN_USAGE,
    )

    total_requests = int(_sum_by_suffix(REQUEST_COUNT, "_total"))
    total_errors = int(_sum_by_suffix(ERROR_COUNT, "_total"))

    total_input_tokens = 0.0
    total_output_tokens = 0.0
    for family in TOKEN_USAGE.collect():
        for sample in family.samples:
            if not sample.name.endswith("_total"):
                continue
            if sample.labels.get("token_type") == "input":
                total_input_tokens += sample.value
            elif sample.labels.get("token_type") == "output":
                total_output_tokens += sample.value

    return MetricsSummary(
        total_requests=total_requests,
        total_errors=total_errors,
        error_rate=(total_errors / total_requests) if total_requests > 0 else 0.0,
        avg_request_latency_ms=_histogram_average_ms(REQUEST_LATENCY),
        total_input_tokens=int(total_input_tokens),
        total_output_tokens=int(total_output_tokens),
        total_estimated_cost_usd=_sum_by_suffix(MODEL_COST, "_total"),
        avg_retrieval_latency_ms=_histogram_average_ms(RETRIEVAL_LATENCY),
        avg_llm_latency_ms=_histogram_average_ms(LLM_LATENCY),
        total_agent_steps=int(_sum_by_suffix(AGENT_STEPS, "_total")),
        total_rate_limit_rejections=int(_sum_by_suffix(RATE_LIMIT_EXCEEDED, "_total")),
    )
