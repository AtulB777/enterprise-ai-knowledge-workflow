import uuid

from httpx import AsyncClient

from app.main import app
from app.services.llm.factory import get_llm_provider
from tests.fakes import FakeLLMProvider, SequencedLLMProvider
from tests.helpers import auth_headers, get_org_id, register_user


def _use_llm(responses: list[str]) -> None:
    # Constructed once, outside the lambda: FastAPI calls this dependency
    # factory on every request, so a lambda that builds a fresh
    # SequencedLLMProvider each time would reset _call_count to 0 on every
    # call — breaking any test (like the approval flow) that spans more than
    # one HTTP request and expects the sequence to continue across them.
    provider = SequencedLLMProvider(responses)
    app.dependency_overrides[get_llm_provider] = lambda: provider


def _restore_default_llm() -> None:
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider()


TOOL_CALL_CALCULATE = (
    '{"action": "tool_call", "tool": "calculate", '
    '"arguments": {"expression": "21 * 2"}, "reasoning": "computing the answer"}'
)
FINAL_ANSWER = '{"action": "final_answer", "answer": "The answer is 42.", "reasoning": "done"}'


async def test_happy_path_completes_with_low_risk_tool(client: AsyncClient) -> None:
    owner = await register_user(client, email="agent-happy@example.com")
    org_id = await get_org_id(client, owner)

    _use_llm([TOOL_CALL_CALCULATE, FINAL_ANSWER])
    try:
        response = await client.post(
            f"/api/v1/agents?organization_id={org_id}",
            headers=auth_headers(owner.access_token),
            json={"goal": "What is 21 times 2?"},
        )
    finally:
        _restore_default_llm()

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    assert body["final_answer"] == "The answer is 42."
    assert len(body["tool_calls"]) == 1
    assert body["tool_calls"][0]["tool_name"] == "calculate"
    assert body["tool_calls"][0]["status"] == "executed"
    assert body["tool_calls"][0]["output_data"]["result"] == 42


async def test_high_risk_tool_pauses_for_approval(client: AsyncClient) -> None:
    owner = await register_user(client, email="agent-pause@example.com")
    org_id = await get_org_id(client, owner)
    upload = await client.post(
        f"/api/v1/documents?organization_id={org_id}",
        headers=auth_headers(owner.access_token),
        files={"file": ("to_delete.txt", b"delete me", "text/plain")},
    )
    document_id = upload.json()["id"]

    delete_action = (
        f'{{"action": "tool_call", "tool": "delete_document", '
        f'"arguments": {{"document_id": "{document_id}", "reason": "cleanup"}}, '
        f'"reasoning": "removing the document"}}'
    )
    _use_llm([delete_action])
    try:
        response = await client.post(
            f"/api/v1/agents?organization_id={org_id}",
            headers=auth_headers(owner.access_token),
            json={"goal": f"Delete document {document_id}"},
        )
    finally:
        _restore_default_llm()

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "awaiting_approval"
    assert len(body["tool_calls"]) == 1
    tool_call = body["tool_calls"][0]
    assert tool_call["tool_name"] == "delete_document"
    assert tool_call["status"] == "awaiting_approval"
    assert tool_call["approval"]["status"] == "pending"

    # The document must NOT have been deleted yet — approval is real
    # workflow state, not UI decoration.
    get_doc = await client.get(
        f"/api/v1/documents/{document_id}?organization_id={org_id}",
        headers=auth_headers(owner.access_token),
    )
    assert get_doc.status_code == 200


async def test_approving_resumes_and_executes_the_action(client: AsyncClient) -> None:
    owner = await register_user(client, email="agent-approve@example.com")
    org_id = await get_org_id(client, owner)
    upload = await client.post(
        f"/api/v1/documents?organization_id={org_id}",
        headers=auth_headers(owner.access_token),
        files={"file": ("to_delete2.txt", b"delete me too", "text/plain")},
    )
    document_id = upload.json()["id"]

    delete_action = (
        f'{{"action": "tool_call", "tool": "delete_document", '
        f'"arguments": {{"document_id": "{document_id}", "reason": "cleanup"}}, '
        f'"reasoning": "removing the document"}}'
    )
    final_after_delete = (
        '{"action": "final_answer", "answer": "The document has been deleted.", '
        '"reasoning": "deletion completed"}'
    )
    _use_llm([delete_action, final_after_delete])
    try:
        start_response = await client.post(
            f"/api/v1/agents?organization_id={org_id}",
            headers=auth_headers(owner.access_token),
            json={"goal": f"Delete document {document_id}"},
        )
        run_id = start_response.json()["id"]
        approval_id = start_response.json()["tool_calls"][0]["approval"]["id"]

        approve_response = await client.post(
            f"/api/v1/agents/approvals/{approval_id}/approve?organization_id={org_id}",
            headers=auth_headers(owner.access_token),
            json={"notes": "looks fine"},
        )
    finally:
        _restore_default_llm()

    assert approve_response.status_code == 200
    body = approve_response.json()
    assert body["id"] == run_id
    assert body["status"] == "completed"
    assert body["final_answer"] == "The document has been deleted."
    delete_call = next(tc for tc in body["tool_calls"] if tc["tool_name"] == "delete_document")
    assert delete_call["status"] == "executed"
    assert delete_call["approval"]["status"] == "approved"

    # The document is now genuinely gone.
    get_doc = await client.get(
        f"/api/v1/documents/{document_id}?organization_id={org_id}",
        headers=auth_headers(owner.access_token),
    )
    assert get_doc.status_code == 404


async def test_rejecting_stops_the_run_without_executing(client: AsyncClient) -> None:
    owner = await register_user(client, email="agent-reject@example.com")
    org_id = await get_org_id(client, owner)
    upload = await client.post(
        f"/api/v1/documents?organization_id={org_id}",
        headers=auth_headers(owner.access_token),
        files={"file": ("keep_me.txt", b"important content", "text/plain")},
    )
    document_id = upload.json()["id"]

    delete_action = (
        f'{{"action": "tool_call", "tool": "delete_document", '
        f'"arguments": {{"document_id": "{document_id}", "reason": "cleanup"}}, '
        f'"reasoning": "removing the document"}}'
    )
    _use_llm([delete_action])
    try:
        start_response = await client.post(
            f"/api/v1/agents?organization_id={org_id}",
            headers=auth_headers(owner.access_token),
            json={"goal": f"Delete document {document_id}"},
        )
        approval_id = start_response.json()["tool_calls"][0]["approval"]["id"]

        reject_response = await client.post(
            f"/api/v1/agents/approvals/{approval_id}/reject?organization_id={org_id}",
            headers=auth_headers(owner.access_token),
            json={"notes": "not authorized"},
        )
    finally:
        _restore_default_llm()

    assert reject_response.status_code == 200
    body = reject_response.json()
    assert body["status"] == "rejected"
    delete_call = next(tc for tc in body["tool_calls"] if tc["tool_name"] == "delete_document")
    assert delete_call["status"] == "rejected"
    assert delete_call["approval"]["status"] == "rejected"

    # The document must still exist — rejection genuinely prevented execution.
    get_doc = await client.get(
        f"/api/v1/documents/{document_id}?organization_id={org_id}",
        headers=auth_headers(owner.access_token),
    )
    assert get_doc.status_code == 200


async def test_max_steps_exceeded_fails_the_run(client: AsyncClient) -> None:
    owner = await register_user(client, email="agent-maxsteps@example.com")
    org_id = await get_org_id(client, owner)

    # Default agent_max_steps=8; 4 tool_call/observation pairs consume all 8
    # steps, so the run must fail on the 5th planning attempt WITHOUT a 5th
    # planner call ever happening (SequencedLLMProvider would raise if it did).
    _use_llm([TOOL_CALL_CALCULATE] * 4)
    try:
        response = await client.post(
            f"/api/v1/agents?organization_id={org_id}",
            headers=auth_headers(owner.access_token),
            json={"goal": "Keep calculating forever"},
        )
    finally:
        _restore_default_llm()

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "failed"
    assert "step count" in body["error_message"].lower()
    assert body["step_count"] == 8


async def test_planner_parse_error_fails_gracefully(client: AsyncClient) -> None:
    owner = await register_user(client, email="agent-parseerror@example.com")
    org_id = await get_org_id(client, owner)

    _use_llm(["This is not JSON at all, just prose."])
    try:
        response = await client.post(
            f"/api/v1/agents?organization_id={org_id}",
            headers=auth_headers(owner.access_token),
            json={"goal": "Do something"},
        )
    finally:
        _restore_default_llm()

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "failed"
    assert "unparseable" in body["error_message"].lower()


async def test_viewer_role_cannot_use_high_risk_tool_even_if_planner_tries(
    client: AsyncClient, db_session
) -> None:
    from sqlalchemy import select

    from app.models.membership import Membership, MembershipRole
    from app.models.user import User

    owner = await register_user(client, email="agent-viewer-owner@example.com")
    org_id = await get_org_id(client, owner)
    upload = await client.post(
        f"/api/v1/documents?organization_id={org_id}",
        headers=auth_headers(owner.access_token),
        files={"file": ("protected.txt", b"protected content", "text/plain")},
    )
    document_id = upload.json()["id"]

    viewer = await register_user(client, email="agent-viewer@example.com")
    result = await db_session.execute(select(User).where(User.email == "agent-viewer@example.com"))
    viewer_user = result.scalar_one()
    db_session.add(
        Membership(
            user_id=viewer_user.id, organization_id=uuid.UUID(org_id), role=MembershipRole.VIEWER
        )
    )
    await db_session.commit()

    delete_action = (
        f'{{"action": "tool_call", "tool": "delete_document", '
        f'"arguments": {{"document_id": "{document_id}", "reason": "cleanup"}}, '
        f'"reasoning": "removing the document"}}'
    )
    final_after_denied = (
        '{"action": "final_answer", "answer": "I am not permitted to do that.", '
        '"reasoning": "permission denied"}'
    )
    _use_llm([delete_action, final_after_denied])
    try:
        response = await client.post(
            f"/api/v1/agents?organization_id={org_id}",
            headers=auth_headers(viewer.access_token),
            json={"goal": f"Delete document {document_id}"},
        )
    finally:
        _restore_default_llm()

    assert response.status_code == 201
    body = response.json()
    delete_call = next(tc for tc in body["tool_calls"] if tc["tool_name"] == "delete_document")
    assert delete_call["status"] == "failed"
    error_lower = delete_call["error_message"].lower()
    assert "permission" in error_lower or "role" in error_lower

    # The document must still exist.
    get_doc = await client.get(
        f"/api/v1/documents/{document_id}?organization_id={org_id}",
        headers=auth_headers(owner.access_token),
    )
    assert get_doc.status_code == 200


async def test_agent_run_is_scoped_to_organization(client: AsyncClient) -> None:
    org_a_owner = await register_user(
        client, email="agent-tenant-a@example.com", organization_name="Agent Org A"
    )
    org_b_owner = await register_user(
        client, email="agent-tenant-b@example.com", organization_name="Agent Org B"
    )
    org_a_id = await get_org_id(client, org_a_owner)

    _use_llm([FINAL_ANSWER])
    try:
        start_response = await client.post(
            f"/api/v1/agents?organization_id={org_a_id}",
            headers=auth_headers(org_a_owner.access_token),
            json={"goal": "Say something"},
        )
    finally:
        _restore_default_llm()
    run_id = start_response.json()["id"]

    response = await client.get(
        f"/api/v1/agents/{run_id}?organization_id={org_a_id}",
        headers=auth_headers(org_b_owner.access_token),
    )

    assert response.status_code == 404


async def test_list_agent_runs(client: AsyncClient) -> None:
    owner = await register_user(client, email="agent-list@example.com")
    org_id = await get_org_id(client, owner)

    _use_llm([FINAL_ANSWER])
    try:
        await client.post(
            f"/api/v1/agents?organization_id={org_id}",
            headers=auth_headers(owner.access_token),
            json={"goal": "First run"},
        )
    finally:
        _restore_default_llm()

    response = await client.get(
        f"/api/v1/agents?organization_id={org_id}", headers=auth_headers(owner.access_token)
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
