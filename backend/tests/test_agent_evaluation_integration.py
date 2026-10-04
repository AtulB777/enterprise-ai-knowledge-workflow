"""Proves evaluation/agent_metrics.py works correctly against real
AgentService runs — not just synthetic data. Reuses the same
SequencedLLMProvider pattern as test_agents_api.py to script real, complete
agent runs through the actual HTTP API, then feeds the real results into
the metric functions.
"""

from httpx import AsyncClient

from app.main import app
from app.services.llm.factory import get_llm_provider
from evaluation.agent_golden_dataset import AGENT_GOLDEN_CASES
from evaluation.agent_metrics import (
    AgentRunOutcome,
    task_success_rate,
    tool_selection_accuracy,
    unnecessary_tool_calls,
)
from tests.fakes import FakeLLMProvider, SequencedLLMProvider
from tests.helpers import auth_headers, get_org_id, register_user


def _use_llm(responses: list[str]) -> None:
    provider = SequencedLLMProvider(responses)
    app.dependency_overrides[get_llm_provider] = lambda: provider


def _restore_default_llm() -> None:
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider()


async def _run_case_and_extract_outcome(
    client: AsyncClient, *, access_token: str, org_id: str, goal: str, responses: list[str]
) -> AgentRunOutcome:
    _use_llm(responses)
    try:
        response = await client.post(
            f"/api/v1/agents?organization_id={org_id}",
            headers=auth_headers(access_token),
            json={"goal": goal},
        )
    finally:
        _restore_default_llm()

    body = response.json()
    return AgentRunOutcome(
        case_id="test",
        completed=(body["status"] == "completed"),
        tool_names_used=[tc["tool_name"] for tc in body["tool_calls"]],
    )


async def test_metrics_reflect_a_real_well_behaved_agent_run(client: AsyncClient) -> None:
    """A run scripted to use exactly the acceptable tool, exactly once, then
    finish — should score perfectly on all three metrics.
    """
    owner = await register_user(client, email="agent-eval-good@example.com")
    org_id = await get_org_id(client, owner)
    case = next(c for c in AGENT_GOLDEN_CASES if c.case_id == "simple-calculation")

    outcome = await _run_case_and_extract_outcome(
        client,
        access_token=owner.access_token,
        org_id=org_id,
        goal=case.goal,
        responses=[
            '{"action": "tool_call", "tool": "calculate", '
            '"arguments": {"expression": "15 * 3"}, "reasoning": "computing"}',
            '{"action": "final_answer", "answer": "45", "reasoning": "done"}',
        ],
    )

    assert task_success_rate([outcome]) == 1.0
    assert tool_selection_accuracy(outcome, case.acceptable_tools) == 1.0
    assert unnecessary_tool_calls(outcome, case.minimum_tool_calls) == 0


async def test_metrics_correctly_penalize_a_real_poorly_behaved_run(client: AsyncClient) -> None:
    """The actual proof: a run that (a) uses a tool outside the acceptable
    set and (b) calls it more times than necessary must score BADLY on
    tool_selection_accuracy and unnecessary_tool_calls — a metrics module
    that only ever reports good scores would be worthless.
    """
    owner = await register_user(client, email="agent-eval-bad@example.com")
    org_id = await get_org_id(client, owner)
    case = next(c for c in AGENT_GOLDEN_CASES if c.case_id == "simple-calculation")

    outcome = await _run_case_and_extract_outcome(
        client,
        access_token=owner.access_token,
        org_id=org_id,
        goal=case.goal,
        responses=[
            # Unnecessary/off-task search_documents call (not "calculate").
            '{"action": "tool_call", "tool": "search_documents", '
            '"arguments": {"query": "math facts"}, "reasoning": "looking around"}',
            '{"action": "tool_call", "tool": "calculate", '
            '"arguments": {"expression": "15 * 3"}, "reasoning": "computing"}',
            '{"action": "final_answer", "answer": "45", "reasoning": "done"}',
        ],
    )

    assert task_success_rate([outcome]) == 1.0  # it did still finish
    accuracy = tool_selection_accuracy(outcome, case.acceptable_tools)
    assert accuracy == 0.5  # 1 of 2 tool calls was acceptable
    assert unnecessary_tool_calls(outcome, case.minimum_tool_calls) == 1  # 2 calls, needed 1


async def test_metrics_reflect_a_failed_run(client: AsyncClient) -> None:
    owner = await register_user(client, email="agent-eval-failed@example.com")
    org_id = await get_org_id(client, owner)
    case = next(c for c in AGENT_GOLDEN_CASES if c.case_id == "simple-calculation")

    outcome = await _run_case_and_extract_outcome(
        client,
        access_token=owner.access_token,
        org_id=org_id,
        goal=case.goal,
        responses=["this is not valid JSON at all"],
    )

    assert outcome.completed is False
    assert task_success_rate([outcome]) == 0.0
