"""Prometheus metrics (spec §29's exact named list) — see ADR-014 decision 2
for why prometheus-client over a custom format, and decision 3 for why this
covers metrics rather than full distributed tracing.

Defined once here, imported and observed from wherever the relevant work
actually happens (the request middleware, LLM provider implementations,
SearchService, AgentRepository) — never redefined per call site.
"""

from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests handled",
    ["method", "path", "status_code"],
)
ERROR_COUNT = Counter(
    "http_errors_total",
    "Total HTTP responses with a 4xx or 5xx status",
    ["method", "path", "status_code"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
)
TOKEN_USAGE = Counter(
    "llm_tokens_total",
    "LLM tokens consumed",
    ["provider", "model", "token_type"],  # token_type: input | output
)
MODEL_COST = Counter(
    "llm_estimated_cost_usd_total",
    "Estimated LLM cost in USD (see app/core/pricing.py — approximate)",
    ["provider", "model"],
)
RETRIEVAL_LATENCY = Histogram(
    "retrieval_duration_seconds",
    "Hybrid search retrieval latency in seconds",
)
LLM_LATENCY = Histogram(
    "llm_request_duration_seconds",
    "LLM completion latency in seconds",
    ["provider", "model"],
)
AGENT_STEPS = Counter(
    "agent_steps_total",
    "Agent state machine steps recorded",
    ["state"],
)
RATE_LIMIT_EXCEEDED = Counter(
    "rate_limit_exceeded_total",
    "Requests rejected for exceeding a rate limit (spec §39)",
    ["scope"],
)
