"""Request-scoped correlation context (ADR-014 decision 1).

`contextvars` (not thread-locals) because the app is fully async — a
contextvar correctly follows one request's coroutine chain even as the
event loop interleaves other requests, where a thread-local would leak
across concurrent requests sharing the same thread.

Nothing here does any logging itself — `app/core/logging.py`'s
`RequestContextFilter` reads these to populate every log record, and
`app/main.py`'s middleware / `app/api/v1/deps.py`'s auth dependencies are
the only things that ever set them.
"""

from contextvars import ContextVar

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("user_id", default=None)
_organization_id: ContextVar[str | None] = ContextVar("organization_id", default=None)


def bind_request_id(request_id: str) -> None:
    _request_id.set(request_id)


def bind_user_id(user_id: str) -> None:
    _user_id.set(user_id)


def bind_organization_id(organization_id: str) -> None:
    _organization_id.set(organization_id)


def get_request_id() -> str | None:
    return _request_id.get()


def get_user_id() -> str | None:
    return _user_id.get()


def get_organization_id() -> str | None:
    return _organization_id.get()


def reset_context() -> None:
    """Called at the start of anything that establishes a fresh logical
    request (the HTTP middleware, and the worker's per-job handling) so
    stale values from a previous request/job sharing the same event-loop
    task machinery can never leak forward.
    """
    _request_id.set(None)
    _user_id.set(None)
    _organization_id.set(None)
