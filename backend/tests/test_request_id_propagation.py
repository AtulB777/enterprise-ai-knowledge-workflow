"""Tests for request_id propagation across the API -> worker boundary
(ADR-014 decision 3) — the practical substitute for full distributed
tracing at this system's scale.
"""

import app.services.document_service as document_service_module
from app.core.config import get_settings
from app.core.request_context import bind_request_id, get_request_id, reset_context
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository
from app.services.document_service import DocumentService
from app.services.storage import LocalFileStorage
from app.workers.tasks import process_document
from tests.fakes import FakeEmbeddingProvider


async def _create_org_and_user(db_session, *, org_name: str, email: str):
    org = await OrganizationRepository(db_session).create_with_unique_slug(name=org_name)
    user = await UserRepository(db_session).create(
        email=email, hashed_password="x", full_name="Propagation Test User"
    )
    await db_session.commit()
    return org, user


async def test_upload_document_enqueues_job_with_the_current_request_id(
    db_session, monkeypatch
) -> None:
    """The enqueueing side: DocumentService must actually pass the
    currently-bound request_id through to the arq job, not just have a
    parameter for it on the worker side that nothing ever populates.
    """
    reset_context()
    bind_request_id("propagation-test-id")

    recorded_calls = []

    class _FakePool:
        async def enqueue_job(self, name, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
            recorded_calls.append((name, args, kwargs))

    async def _fake_get_arq_pool():
        return _FakePool()

    monkeypatch.setattr(document_service_module, "get_arq_pool", _fake_get_arq_pool)

    settings = get_settings()
    storage = LocalFileStorage(settings.storage_root)
    service = DocumentService(db_session, settings, storage)
    org, user = await _create_org_and_user(
        db_session, org_name="Propagation Test Org", email="propagation1@example.com"
    )

    await service.upload_document(
        organization_id=org.id,
        uploaded_by_user_id=user.id,
        collection_id=None,
        filename="test.txt",
        content=b"hello",
    )

    assert len(recorded_calls) == 1
    name, _args, kwargs = recorded_calls[0]
    assert name == "process_document"
    assert kwargs["request_id"] == "propagation-test-id"


async def test_upload_document_enqueues_with_none_request_id_when_none_bound(
    db_session, monkeypatch
) -> None:
    """A job triggered without an originating HTTP request (e.g. a direct
    script) should enqueue cleanly with request_id=None, not crash or
    silently invent one.
    """
    reset_context()

    recorded_calls = []

    class _FakePool:
        async def enqueue_job(self, name, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
            recorded_calls.append((name, args, kwargs))

    async def _fake_get_arq_pool():
        return _FakePool()

    monkeypatch.setattr(document_service_module, "get_arq_pool", _fake_get_arq_pool)

    settings = get_settings()
    storage = LocalFileStorage(settings.storage_root)
    service = DocumentService(db_session, settings, storage)
    org, user = await _create_org_and_user(
        db_session, org_name="No Request Org", email="propagation2@example.com"
    )

    await service.upload_document(
        organization_id=org.id,
        uploaded_by_user_id=user.id,
        collection_id=None,
        filename="test.txt",
        content=b"hello",
    )

    assert recorded_calls[0][2]["request_id"] is None


async def test_process_document_binds_the_propagated_request_id(db_session) -> None:
    """The worker side: given a request_id, process_document binds it into
    its own logging context for the job's execution — the mechanism that
    makes the worker's logs correlate with the original upload request.
    """
    reset_context()
    settings = get_settings()
    storage = LocalFileStorage(settings.storage_root)
    service = DocumentService(db_session, settings, storage)
    org, user = await _create_org_and_user(
        db_session, org_name="Worker Propagation Org", email="propagation3@example.com"
    )
    document = await service.upload_document(
        organization_id=org.id,
        uploaded_by_user_id=user.id,
        collection_id=None,
        filename="worker-test.txt",
        content=b"real content for the worker to process",
    )

    # Simulate a different process/context than the one that enqueued the
    # job — reset first, so the only way get_request_id() below could
    # return the expected value is if process_document itself bound it.
    reset_context()
    assert get_request_id() is None

    await process_document(
        ctx={},
        document_id=str(document.id),
        embedding_provider=FakeEmbeddingProvider(),
        request_id="worker-correlation-test-id",
    )

    assert get_request_id() == "worker-correlation-test-id"


async def test_process_document_without_request_id_does_not_crash(db_session) -> None:
    reset_context()
    settings = get_settings()
    storage = LocalFileStorage(settings.storage_root)
    service = DocumentService(db_session, settings, storage)
    org, user = await _create_org_and_user(
        db_session, org_name="No Correlation Org", email="propagation4@example.com"
    )
    document = await service.upload_document(
        organization_id=org.id,
        uploaded_by_user_id=user.id,
        collection_id=None,
        filename="no-correlation.txt",
        content=b"content",
    )

    await process_document(
        ctx={}, document_id=str(document.id), embedding_provider=FakeEmbeddingProvider()
    )

    assert get_request_id() is None
