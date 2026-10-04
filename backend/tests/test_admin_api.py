import uuid

from httpx import AsyncClient

from app.core.config import get_settings
from app.core.security import create_access_token
from app.models.membership import Membership, MembershipRole
from app.repositories.evaluation_repository import EvaluationRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository
from tests.helpers import auth_headers, get_org_id, register_user


async def _create_non_admin_user_token(db_session, *, org_id: str, role: MembershipRole) -> str:
    """A user who is NOT an admin of anything — unlike register_user()
    (which always makes the registering user ADMIN of their own new org),
    this constructs a user directly with only a single, non-admin
    membership, to prove require_platform_admin actually rejects someone
    without admin access anywhere, not just someone who happens to lack it
    in the org being viewed (there's no such org-scoping here at all — see
    ADR-018 decision 4).
    """
    user = await UserRepository(db_session).create(
        email=f"non-admin-{uuid.uuid4()}@example.com",
        hashed_password="not-a-real-hash",
        full_name="Non Admin",
    )
    db_session.add(Membership(user_id=user.id, organization_id=uuid.UUID(org_id), role=role))
    await db_session.commit()

    settings = get_settings()
    return create_access_token(
        subject=str(user.id),
        secret=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
        expires_minutes=30,
    )


async def test_non_admin_is_rejected(client: AsyncClient, db_session) -> None:
    owner = await register_user(client, email="admin-gate-owner@example.com")
    org_id = await get_org_id(client, owner)
    token = await _create_non_admin_user_token(
        db_session, org_id=org_id, role=MembershipRole.VIEWER
    )

    response = await client.get("/api/v1/admin/metrics-summary", headers=auth_headers(token))

    assert response.status_code == 403


async def test_org_admin_is_allowed(client: AsyncClient) -> None:
    # register_user() makes the founder ADMIN of their own new org — no
    # special setup needed to prove the allowed path.
    owner = await register_user(client, email="admin-gate-allowed@example.com")

    response = await client.get(
        "/api/v1/admin/metrics-summary", headers=auth_headers(owner.access_token)
    )

    assert response.status_code == 200


async def test_admin_routes_require_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/admin/metrics-summary")
    assert response.status_code == 401


async def test_metrics_summary_reflects_real_activity(client: AsyncClient) -> None:
    owner = await register_user(client, email="metrics-summary-real@example.com")

    before = await client.get(
        "/api/v1/admin/metrics-summary", headers=auth_headers(owner.access_token)
    )
    before_total = before.json()["total_requests"]

    # A few real, arbitrary requests to genuinely move the counter.
    await client.get("/api/v1/health")
    await client.get("/api/v1/health")

    after = await client.get(
        "/api/v1/admin/metrics-summary", headers=auth_headers(owner.access_token)
    )
    after_total = after.json()["total_requests"]

    assert after_total > before_total


async def test_evaluation_list_is_platform_wide_not_org_scoped(
    client: AsyncClient, db_session
) -> None:
    """The actual point of ADR-018 decision 2: an evaluation run created
    under a completely different (throwaway) organization than the viewing
    admin's own org must still show up — because these routes are
    deliberately not tenant-scoped at all.
    """
    owner = await register_user(client, email="eval-platform-wide@example.com")

    unrelated_org = await OrganizationRepository(db_session).create_with_unique_slug(
        name="Totally Unrelated Eval Org"
    )
    await db_session.commit()
    eval_repo = EvaluationRepository(db_session)
    run = await eval_repo.create_run(
        organization_id=unrelated_org.id, dataset_version="v-test-platform-wide"
    )
    await eval_repo.complete_run(run, summary_metrics={"recall_at_5": 0.9})

    response = await client.get(
        "/api/v1/admin/evaluations", headers=auth_headers(owner.access_token)
    )

    assert response.status_code == 200
    body = response.json()
    run_ids = [item["id"] for item in body["items"]]
    assert str(run.id) in run_ids


async def test_evaluation_run_detail_includes_results(client: AsyncClient, db_session) -> None:
    owner = await register_user(client, email="eval-detail-real@example.com")
    org = await OrganizationRepository(db_session).create_with_unique_slug(name="Eval Detail Org")
    await db_session.commit()
    eval_repo = EvaluationRepository(db_session)
    run = await eval_repo.create_run(organization_id=org.id, dataset_version="v-test-detail")
    await eval_repo.add_result(
        run_id=run.id,
        case_id="case-1",
        query="What is the vacation policy?",
        metrics={"recall_at_5": 1.0, "citation_precision": 1.0},
        latency_ms=123.4,
        error_message=None,
    )
    await eval_repo.complete_run(run, summary_metrics={"recall_at_5": 1.0})

    response = await client.get(
        f"/api/v1/admin/evaluations/{run.id}", headers=auth_headers(owner.access_token)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert len(body["results"]) == 1
    assert body["results"][0]["case_id"] == "case-1"
    assert body["results"][0]["metrics"]["recall_at_5"] == 1.0


async def test_evaluation_run_not_found_returns_404(client: AsyncClient) -> None:
    owner = await register_user(client, email="eval-404@example.com")

    response = await client.get(
        f"/api/v1/admin/evaluations/{uuid.uuid4()}", headers=auth_headers(owner.access_token)
    )

    assert response.status_code == 404
