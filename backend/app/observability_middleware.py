"""Request correlation + observability middleware (ADR-014 decision 1).

Deliberately a pure ASGI middleware (`__call__(scope, receive, send)`), NOT
`@app.middleware("http")` / `BaseHTTPMiddleware`. This is a real, verified
constraint, not a style preference: `BaseHTTPMiddleware` runs the downstream
app in a separate task via an internal stream, which means contextvars set
deep in request handling (e.g. `bind_user_id()` in `get_current_user`) never
propagate back out to code that runs after `call_next()` returns — confirmed
empirically here (a live authenticated request's "request_completed" log
line was missing `user_id` entirely under `BaseHTTPMiddleware`, despite auth
having definitely succeeded). A pure ASGI middleware runs the whole
downstream chain in the same task/coroutine as this middleware, so
contextvars set anywhere downstream are visible here afterward, as intended.
"""

import logging
import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.metrics import ERROR_COUNT, REQUEST_COUNT, REQUEST_LATENCY
from app.core.request_context import bind_request_id, reset_context

logger = logging.getLogger("app")


class ObservabilityMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        reset_context()
        request_id = _extract_request_id(scope) or str(uuid.uuid4())
        bind_request_id(request_id)

        status_holder: dict[str, int] = {}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status_code"] = message["status"]
                headers = MutableHeaders(scope=message)
                headers.append("X-Request-ID", request_id)
            await send(message)

        start = time.monotonic()
        await self.app(scope, receive, send_wrapper)
        elapsed_seconds = time.monotonic() - start

        # Route template (e.g. "/api/v1/documents/{document_id}"), not the
        # resolved path with real IDs substituted in — using the raw path
        # as a Prometheus label would create one label series per unique ID
        # ever requested, a well-known high-cardinality anti-pattern.
        # Starlette's router mutates this same scope dict in place during
        # matching, so by the time self.app() above has returned, scope
        # "route" is populated for any request that matched a real route.
        route = scope.get("route")
        path_label = route.path if route is not None else scope.get("path", "unknown")
        method = scope.get("method", "UNKNOWN")
        status_code = status_holder.get("status_code", 500)

        REQUEST_COUNT.labels(method=method, path=path_label, status_code=str(status_code)).inc()
        REQUEST_LATENCY.labels(method=method, path=path_label).observe(elapsed_seconds)
        if status_code >= 400:
            ERROR_COUNT.labels(method=method, path=path_label, status_code=str(status_code)).inc()

        logger.info(
            "request_completed",
            extra={
                "http_method": method,
                "path": path_label,
                "status_code": status_code,
                "latency_ms": round(elapsed_seconds * 1000, 2),
            },
        )


def _extract_request_id(scope: Scope) -> str | None:
    headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
    for name, value in headers:
        if name == b"x-request-id":
            decoded: str = value.decode("latin-1")
            return decoded
    return None
