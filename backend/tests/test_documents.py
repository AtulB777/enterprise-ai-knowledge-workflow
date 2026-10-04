import uuid

from httpx import AsyncClient
from sqlalchemy import select

from app.models.document_chunk import DocumentChunk
from app.models.membership import Membership, MembershipRole
from app.models.user import User
from app.workers.tasks import process_document
from tests.fakes import FakeEmbeddingProvider
from tests.helpers import auth_headers, get_org_id, register_user


async def _upload(
    client: AsyncClient,
    *,
    access_token: str,
    organization_id: str,
    filename: str = "notes.txt",
    content: bytes = b"Quarterly planning notes.",
    collection_id: str | None = None,
):
    data = {"collection_id": collection_id} if collection_id else {}
    return await client.post(
        f"/api/v1/documents?organization_id={organization_id}",
        headers=auth_headers(access_token),
        files={"file": (filename, content, "text/plain")},
        data=data,
    )


async def _add_membership(
    db_session, *, email: str, organization_id: str, role: MembershipRole
) -> None:
    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    db_session.add(
        Membership(user_id=user.id, organization_id=uuid.UUID(organization_id), role=role)
    )
    await db_session.commit()


async def test_upload_creates_document_in_pending_status(client: AsyncClient) -> None:
    owner = await register_user(client, email="uploader@example.com")
    org_id = await get_org_id(client, owner)

    response = await _upload(client, access_token=owner.access_token, organization_id=org_id)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "pending"
    assert body["original_filename"] == "notes.txt"
    assert body["content_type"] == "text/plain"


async def test_upload_rejects_invalid_file_type(client: AsyncClient) -> None:
    owner = await register_user(client, email="badupload@example.com")
    org_id = await get_org_id(client, owner)

    response = await _upload(
        client,
        access_token=owner.access_token,
        organization_id=org_id,
        filename="malware.exe",
        content=b"MZ\x90\x00fake-binary",
    )

    assert response.status_code == 422


async def test_viewer_role_cannot_upload_documents(client: AsyncClient, db_session) -> None:
    owner = await register_user(client, email="doc-org-owner@example.com")
    org_id = await get_org_id(client, owner)

    viewer = await register_user(client, email="doc-viewer@example.com")
    await _add_membership(
        db_session,
        email="doc-viewer@example.com",
        organization_id=org_id,
        role=MembershipRole.VIEWER,
    )

    response = await _upload(client, access_token=viewer.access_token, organization_id=org_id)

    assert response.status_code == 403


async def test_worker_processes_uploaded_text_file_end_to_end(
    client: AsyncClient, db_session
) -> None:
    """The real pipeline test: upload via the API, run the actual worker task
    function (the same code arq would run, with a fake embedding provider
    injected — see ADR-008 for why the real model can't run in this sandbox),
    then confirm the document transitions to COMPLETED with genuinely
    extracted text AND real chunk rows with real vectors in pgvector.
    """
    owner = await register_user(client, email="pipeline@example.com")
    org_id = await get_org_id(client, owner)

    upload_response = await _upload(
        client,
        access_token=owner.access_token,
        organization_id=org_id,
        filename="memo.txt",
        content=b"The board approved the new budget.",
    )
    document_id = upload_response.json()["id"]

    await process_document(
        ctx={}, document_id=document_id, embedding_provider=FakeEmbeddingProvider()
    )

    get_response = await client.get(
        f"/api/v1/documents/{document_id}?organization_id={org_id}",
        headers=auth_headers(owner.access_token),
    )
    assert get_response.status_code == 200
    body = get_response.json()
    assert body["status"] == "completed"
    assert body["extracted_text"] == "The board approved the new budget."
    assert body["extracted_char_count"] == len("The board approved the new budget.")

    chunk_result = await db_session.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == uuid.UUID(document_id))
    )
    chunks = chunk_result.scalars().all()
    assert len(chunks) == 1
    assert chunks[0].content == "The board approved the new budget."
    assert chunks[0].embedding_model == "fake-hashing-embedding-test-only"
    assert len(chunks[0].embedding) == 384


async def test_worker_marks_broken_content_as_failed(client: AsyncClient) -> None:
    """Invalid UTF-8 passes upload validation's MIME sniff (libmagic reports
    text/plain for the readable prefix) but must fail cleanly at extraction,
    with a stored reason — not crash the worker or silently 'succeed' empty.
    """
    owner = await register_user(client, email="failcase@example.com")
    org_id = await get_org_id(client, owner)

    upload_response = await _upload(
        client,
        access_token=owner.access_token,
        organization_id=org_id,
        filename="broken.txt",
        content=b"Valid start then \xff\xfe broken bytes",
    )
    document_id = upload_response.json()["id"]

    await process_document(
        ctx={}, document_id=document_id, embedding_provider=FakeEmbeddingProvider()
    )

    get_response = await client.get(
        f"/api/v1/documents/{document_id}?organization_id={org_id}",
        headers=auth_headers(owner.access_token),
    )
    body = get_response.json()
    assert body["status"] == "failed"
    assert body["processing_error"]


async def test_list_documents_paginates(client: AsyncClient) -> None:
    owner = await register_user(client, email="lister@example.com")
    org_id = await get_org_id(client, owner)
    for i in range(3):
        await _upload(
            client,
            access_token=owner.access_token,
            organization_id=org_id,
            filename=f"doc{i}.txt",
            content=f"content {i}".encode(),
        )

    response = await client.get(
        f"/api/v1/documents?organization_id={org_id}&limit=2&offset=0",
        headers=auth_headers(owner.access_token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2


async def test_get_unknown_document_returns_404(client: AsyncClient) -> None:
    owner = await register_user(client, email="notfound@example.com")
    org_id = await get_org_id(client, owner)
    fake_id = str(uuid.uuid4())

    response = await client.get(
        f"/api/v1/documents/{fake_id}?organization_id={org_id}",
        headers=auth_headers(owner.access_token),
    )

    assert response.status_code == 404


async def test_cross_tenant_document_access_returns_404(client: AsyncClient) -> None:
    org_a_owner = await register_user(
        client, email="doc-a-owner@example.com", organization_name="Doc Org A"
    )
    org_b_owner = await register_user(
        client, email="doc-b-owner@example.com", organization_name="Doc Org B"
    )
    org_a_id = await get_org_id(client, org_a_owner)

    upload_response = await _upload(
        client, access_token=org_a_owner.access_token, organization_id=org_a_id
    )
    document_id = upload_response.json()["id"]

    # Org B's owner tries to reach org A's document by (correctly) naming
    # org A as the target organization — but they aren't a member of it.
    response = await client.get(
        f"/api/v1/documents/{document_id}?organization_id={org_a_id}",
        headers=auth_headers(org_b_owner.access_token),
    )

    assert response.status_code == 404


async def test_manager_can_delete_document(client: AsyncClient) -> None:
    owner = await register_user(client, email="deleter@example.com")
    org_id = await get_org_id(client, owner)
    upload_response = await _upload(client, access_token=owner.access_token, organization_id=org_id)
    document_id = upload_response.json()["id"]

    delete_response = await client.delete(
        f"/api/v1/documents/{document_id}?organization_id={org_id}",
        headers=auth_headers(owner.access_token),
    )
    assert delete_response.status_code == 204

    get_response = await client.get(
        f"/api/v1/documents/{document_id}?organization_id={org_id}",
        headers=auth_headers(owner.access_token),
    )
    assert get_response.status_code == 404


async def test_employee_role_cannot_delete_document(client: AsyncClient, db_session) -> None:
    owner = await register_user(client, email="del-org-owner@example.com")
    org_id = await get_org_id(client, owner)
    upload_response = await _upload(client, access_token=owner.access_token, organization_id=org_id)
    document_id = upload_response.json()["id"]

    employee = await register_user(client, email="del-employee@example.com")
    await _add_membership(
        db_session,
        email="del-employee@example.com",
        organization_id=org_id,
        role=MembershipRole.EMPLOYEE,
    )

    response = await client.delete(
        f"/api/v1/documents/{document_id}?organization_id={org_id}",
        headers=auth_headers(employee.access_token),
    )

    assert response.status_code == 403
