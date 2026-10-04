"""Proves the agent system emits real structured log lines for step
transitions and tool calls (spec §29's "tool calls" field) — not just the
AGENT_STEPS metric increment. Reuses test_agents_api.py's SequencedLLMProvider
pattern to run a real agent through the real HTTP API.
"""

import logging

from httpx import AsyncClient

from app.main import app
from app.services.llm.factory import get_llm_provider
from tests.fakes import FakeLLMProvider, SequencedLLMProvider
from tests.helpers import auth_headers, get_org_id, register_user


def _use_llm(responses: list[str]) -> None:
    provider = SequencedLLMProvider(responses)
    app.dependency_overrides[get_llm_provider] = lambda: provider


def _restore_default_llm() -> None:
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider()


async def test_real_agent_run_emits_step_and_tool_call_logs(client: AsyncClient, caplog) -> None:
    owner = await register_user(client, email="agent-logging@example.com")
    org_id = await get_org_id(client, owner)

    _use_llm(
        [
            '{"action": "tool_call", "tool": "calculate", '
            '"arguments": {"expression": "6 * 7"}, "reasoning": "computing"}',
            '{"action": "final_answer", "answer": "42", "reasoning": "done"}',
        ]
    )
    try:
        with caplog.at_level(logging.INFO, logger="app.agents"):
            response = await client.post(
                f"/api/v1/agents?organization_id={org_id}",
                headers=auth_headers(owner.access_token),
                json={"goal": "What is 6 times 7?"},
            )
    finally:
        _restore_default_llm()

    assert response.status_code == 201

    messages = [r.message for r in caplog.records]
    assert "agent_step" in messages
    assert "tool_call_selected" in messages
    assert "tool_call_executed" in messages

    tool_call_record = next(r for r in caplog.records if r.message == "tool_call_selected")
    assert tool_call_record.tool_name == "calculate"
    assert tool_call_record.risk_level == "low"


async def test_approval_decision_is_logged(client: AsyncClient, caplog) -> None:
    owner = await register_user(client, email="agent-approval-logging@example.com")
    org_id = await get_org_id(client, owner)

    upload = await client.post(
        f"/api/v1/documents?organization_id={org_id}",
        headers=auth_headers(owner.access_token),
        files={"file": ("delete-me.txt", b"content", "text/plain")},
    )
    document_id = upload.json()["id"]

    _use_llm(
        [
            f'{{"action": "tool_call", "tool": "delete_document", '
            f'"arguments": {{"document_id": "{document_id}", "reason": "cleanup"}}, '
            f'"reasoning": "removing"}}',
        ]
    )
    try:
        start_response = await client.post(
            f"/api/v1/agents?organization_id={org_id}",
            headers=auth_headers(owner.access_token),
            json={"goal": f"Delete document {document_id}"},
        )
        approval_id = start_response.json()["tool_calls"][0]["approval"]["id"]

        _use_llm(['{"action": "final_answer", "answer": "done", "reasoning": "done"}'])
        with caplog.at_level(logging.INFO, logger="app.agents"):
            await client.post(
                f"/api/v1/agents/approvals/{approval_id}/approve?organization_id={org_id}",
                headers=auth_headers(owner.access_token),
                json={},
            )
    finally:
        _restore_default_llm()

    approval_records = [r for r in caplog.records if r.message == "approval_decided"]
    assert len(approval_records) == 1
    assert approval_records[0].decision == "approved"
