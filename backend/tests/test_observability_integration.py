from httpx import AsyncClient

from app.core.metrics import AGENT_STEPS, RETRIEVAL_LATENCY
from tests.helpers import auth_headers, get_org_id, register_user


def _histogram_count(histogram, **labels) -> float:
    for metric in histogram.collect():
        for sample in metric.samples:
            if sample.name.endswith("_count") and sample.labels == labels:
                return sample.value
    return 0.0


def _counter_value(counter, **labels) -> float:
    for metric in counter.collect():
        for sample in metric.samples:
            if sample.name.endswith("_total") and sample.labels == labels:
                return sample.value
    return 0.0


async def test_response_includes_x_request_id_header(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert "x-request-id" in response.headers
    # A real UUID-shaped value, not empty/placeholder.
    assert len(response.headers["x-request-id"]) == 36


async def test_client_supplied_request_id_is_honored(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health", headers={"X-Request-ID": "my-correlation-id"})
    assert response.headers["x-request-id"] == "my-correlation-id"


async def test_error_response_still_carries_the_client_supplied_request_id(
    client: AsyncClient,
) -> None:
    """Proves the request_id used in the error response BODY (not just the
    header) is the same one the client supplied — before ADR-014, error
    handlers minted their own throwaway UUID, discarding any client
    correlation ID.
    """
    owner = await register_user(client, email="obs-error-correlation@example.com")
    org_id = await get_org_id(client, owner)

    response = await client.get(
        f"/api/v1/documents/not-a-valid-uuid?organization_id={org_id}",
        headers={**auth_headers(owner.access_token), "X-Request-ID": "client-error-correlation-id"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["request_id"] == "client-error-correlation-id"


async def test_metrics_endpoint_returns_prometheus_format(client: AsyncClient) -> None:
    await client.get("/api/v1/health")

    response = await client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    body = response.text
    assert "http_requests_total" in body
    assert "http_request_duration_seconds" in body


async def test_metrics_endpoint_does_not_require_authentication(client: AsyncClient) -> None:
    response = await client.get("/metrics")
    assert response.status_code == 200


async def test_real_search_call_increments_retrieval_latency(client: AsyncClient) -> None:
    owner = await register_user(client, email="obs-search@example.com")
    org_id = await get_org_id(client, owner)

    before = _histogram_count(RETRIEVAL_LATENCY)

    await client.post(
        f"/api/v1/search?organization_id={org_id}",
        headers=auth_headers(owner.access_token),
        json={"query": "anything"},
    )

    after = _histogram_count(RETRIEVAL_LATENCY)
    assert after - before == 1


async def test_real_agent_run_increments_agent_steps(client: AsyncClient) -> None:
    from app.main import app
    from app.services.llm.factory import get_llm_provider
    from tests.fakes import FakeLLMProvider, SequencedLLMProvider

    owner = await register_user(client, email="obs-agent@example.com")
    org_id = await get_org_id(client, owner)

    before_planning = _counter_value(AGENT_STEPS, state="planning")

    provider = SequencedLLMProvider(
        ['{"action": "final_answer", "answer": "done", "reasoning": "nothing needed"}']
    )
    app.dependency_overrides[get_llm_provider] = lambda: provider
    try:
        await client.post(
            f"/api/v1/agents?organization_id={org_id}",
            headers=auth_headers(owner.access_token),
            json={"goal": "Say hello."},
        )
    finally:
        app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider()

    after_planning = _counter_value(AGENT_STEPS, state="planning")
    assert after_planning - before_planning == 1
