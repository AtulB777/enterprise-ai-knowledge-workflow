import uuid

from httpx import AsyncClient

from app.main import app
from app.services.llm.factory import get_llm_provider
from app.workers.tasks import process_document
from tests.fakes import FakeEmbeddingProvider, FakeLLMProvider
from tests.helpers import auth_headers, get_org_id, register_user


async def _upload_and_process(
    client: AsyncClient, *, access_token: str, organization_id: str, filename: str, content: bytes
) -> str:
    response = await client.post(
        f"/api/v1/documents?organization_id={organization_id}",
        headers=auth_headers(access_token),
        files={"file": (filename, content, "text/plain")},
    )
    document_id = response.json()["id"]
    await process_document(
        ctx={}, document_id=document_id, embedding_provider=FakeEmbeddingProvider()
    )
    return document_id


async def _create_conversation(
    client: AsyncClient, *, access_token: str, organization_id: str
) -> str:
    response = await client.post(
        f"/api/v1/conversations?organization_id={organization_id}",
        headers=auth_headers(access_token),
    )
    return response.json()["id"]


async def test_create_conversation(client: AsyncClient) -> None:
    owner = await register_user(client, email="conv-owner@example.com")
    org_id = await get_org_id(client, owner)

    response = await client.post(
        f"/api/v1/conversations?organization_id={org_id}", headers=auth_headers(owner.access_token)
    )

    assert response.status_code == 201
    assert response.json()["title"] is None


async def test_ask_question_with_no_documents_returns_no_evidence_response(
    client: AsyncClient,
) -> None:
    owner = await register_user(client, email="conv-noevidence@example.com")
    org_id = await get_org_id(client, owner)
    conversation_id = await _create_conversation(
        client, access_token=owner.access_token, organization_id=org_id
    )

    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages?organization_id={org_id}",
        headers=auth_headers(owner.access_token),
        json={"question": "What is our vacation policy?"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "assistant"
    assert "don't have" in body["content"].lower()
    assert body["citations"] == []


async def test_ask_question_returns_grounded_answer_with_citations(client: AsyncClient) -> None:
    owner = await register_user(client, email="conv-grounded@example.com")
    org_id = await get_org_id(client, owner)

    await _upload_and_process(
        client,
        access_token=owner.access_token,
        organization_id=org_id,
        filename="vacation_policy.txt",
        content=b"Employees receive 20 days of paid vacation per year.",
    )
    conversation_id = await _create_conversation(
        client, access_token=owner.access_token, organization_id=org_id
    )

    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages?organization_id={org_id}",
        headers=auth_headers(owner.access_token),
        json={"question": "How many vacation days do employees get?"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "assistant"
    assert len(body["citations"]) == 1
    citation = body["citations"][0]
    assert citation["document_filename"] == "vacation_policy.txt"
    assert "20 days" in citation["chunk_content"]
    assert citation["citation_number"] == 1


async def test_conversation_title_set_from_first_question(client: AsyncClient) -> None:
    owner = await register_user(client, email="conv-title@example.com")
    org_id = await get_org_id(client, owner)
    conversation_id = await _create_conversation(
        client, access_token=owner.access_token, organization_id=org_id
    )

    await client.post(
        f"/api/v1/conversations/{conversation_id}/messages?organization_id={org_id}",
        headers=auth_headers(owner.access_token),
        json={"question": "What is our refund policy?"},
    )

    get_response = await client.get(
        f"/api/v1/conversations/{conversation_id}?organization_id={org_id}",
        headers=auth_headers(owner.access_token),
    )
    assert get_response.json()["title"] == "What is our refund policy?"


async def test_get_conversation_returns_full_message_history(client: AsyncClient) -> None:
    owner = await register_user(client, email="conv-history@example.com")
    org_id = await get_org_id(client, owner)
    await _upload_and_process(
        client,
        access_token=owner.access_token,
        organization_id=org_id,
        filename="handbook.txt",
        content=b"Remote work is permitted up to three days per week.",
    )
    conversation_id = await _create_conversation(
        client, access_token=owner.access_token, organization_id=org_id
    )
    await client.post(
        f"/api/v1/conversations/{conversation_id}/messages?organization_id={org_id}",
        headers=auth_headers(owner.access_token),
        json={"question": "How many remote days are allowed?"},
    )

    response = await client.get(
        f"/api/v1/conversations/{conversation_id}?organization_id={org_id}",
        headers=auth_headers(owner.access_token),
    )

    assert response.status_code == 200
    messages = response.json()["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "How many remote days are allowed?"
    assert messages[1]["role"] == "assistant"
    assert len(messages[1]["citations"]) == 1


async def test_hallucinated_citation_is_not_persisted(client: AsyncClient) -> None:
    """End-to-end proof of spec §18: even if the model output contains a
    citation number with no corresponding retrieved document, no Citation
    row is created for it.
    """
    owner = await register_user(client, email="conv-hallucinated@example.com")
    org_id = await get_org_id(client, owner)
    await _upload_and_process(
        client,
        access_token=owner.access_token,
        organization_id=org_id,
        filename="doc.txt",
        content=b"Some real content here.",
    )
    conversation_id = await _create_conversation(
        client, access_token=owner.access_token, organization_id=org_id
    )

    # Temporarily swap in an LLM that hallucinates an out-of-range citation.
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider(
        response_text="This cites a document that does not exist [99]."
    )
    try:
        response = await client.post(
            f"/api/v1/conversations/{conversation_id}/messages?organization_id={org_id}",
            headers=auth_headers(owner.access_token),
            json={"question": "Tell me something."},
        )
    finally:
        app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider()

    assert response.status_code == 201
    assert response.json()["citations"] == []


async def test_manager_can_delete_conversation(client: AsyncClient) -> None:
    owner = await register_user(client, email="conv-delete@example.com")
    org_id = await get_org_id(client, owner)
    conversation_id = await _create_conversation(
        client, access_token=owner.access_token, organization_id=org_id
    )

    delete_response = await client.delete(
        f"/api/v1/conversations/{conversation_id}?organization_id={org_id}",
        headers=auth_headers(owner.access_token),
    )
    assert delete_response.status_code == 204

    get_response = await client.get(
        f"/api/v1/conversations/{conversation_id}?organization_id={org_id}",
        headers=auth_headers(owner.access_token),
    )
    assert get_response.status_code == 404


async def test_conversation_is_scoped_to_organization(client: AsyncClient) -> None:
    org_a_owner = await register_user(
        client, email="conv-tenant-a@example.com", organization_name="Conv Org A"
    )
    org_b_owner = await register_user(
        client, email="conv-tenant-b@example.com", organization_name="Conv Org B"
    )
    org_a_id = await get_org_id(client, org_a_owner)
    conversation_id = await _create_conversation(
        client, access_token=org_a_owner.access_token, organization_id=org_a_id
    )

    response = await client.get(
        f"/api/v1/conversations/{conversation_id}?organization_id={org_a_id}",
        headers=auth_headers(org_b_owner.access_token),
    )

    assert response.status_code == 404


async def test_ask_question_on_unknown_conversation_returns_404(client: AsyncClient) -> None:
    owner = await register_user(client, email="conv-unknown@example.com")
    org_id = await get_org_id(client, owner)
    fake_id = str(uuid.uuid4())

    response = await client.post(
        f"/api/v1/conversations/{fake_id}/messages?organization_id={org_id}",
        headers=auth_headers(owner.access_token),
        json={"question": "anything"},
    )

    assert response.status_code == 404
