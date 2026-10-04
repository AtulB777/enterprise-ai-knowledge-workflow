from app.core.request_context import (
    bind_organization_id,
    bind_request_id,
    bind_user_id,
    get_organization_id,
    get_request_id,
    get_user_id,
    reset_context,
)


def test_bind_and_get_request_id() -> None:
    reset_context()
    assert get_request_id() is None
    bind_request_id("abc-123")
    assert get_request_id() == "abc-123"


def test_bind_and_get_user_id() -> None:
    reset_context()
    bind_user_id("user-1")
    assert get_user_id() == "user-1"


def test_bind_and_get_organization_id() -> None:
    reset_context()
    bind_organization_id("org-1")
    assert get_organization_id() == "org-1"


def test_reset_context_clears_all_fields() -> None:
    bind_request_id("abc-123")
    bind_user_id("user-1")
    bind_organization_id("org-1")

    reset_context()

    assert get_request_id() is None
    assert get_user_id() is None
    assert get_organization_id() is None
