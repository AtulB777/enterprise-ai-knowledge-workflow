"""FastAPI application entrypoint."""

import logging
from typing import Any

from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.request_context import get_request_id
from app.observability_middleware import ObservabilityMiddleware
from app.security_headers_middleware import SecurityHeadersMiddleware

configure_logging()
logger = logging.getLogger("app")

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    debug=settings.debug,
)

# Outermost layer (added last — Starlette's middleware stack wraps in
# reverse-registration order) so these headers land on every response,
# including error responses the layers below produce.
app.add_middleware(SecurityHeadersMiddleware)

# Pure ASGI middleware, not @app.middleware("http") — see
# observability_middleware.py's docstring for why (a real, verified
# BaseHTTPMiddleware context-propagation limitation, not a style choice).
app.add_middleware(ObservabilityMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    # Deliberately unauthenticated (ADR-014 decision 2) — matches standard
    # Prometheus practice of network-level rather than app-level protection
    # for scrape endpoints. Mounted at root, not under /api/v1: this is
    # operational infrastructure, not a versioned business API resource.
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


def _error_body(code: str, message: str, request_id: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "request_id": request_id}}


def _current_request_id() -> str:
    # Always bound by ObservabilityMiddleware before any handler runs — the
    # "unknown" fallback only matters for the theoretical case of an
    # exception raised before that binding completes.
    return get_request_id() or "unknown"


_STATUS_CODE_NAMES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
}


@app.exception_handler(HTTPException)
async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    request_id = _current_request_id()
    logger.warning(
        "http_exception",
        extra={"request_id": request_id, "status_code": exc.status_code, "path": request.url.path},
    )
    code = _STATUS_CODE_NAMES.get(exc.status_code, "HTTP_ERROR")
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(code, str(exc.detail), request_id),
        # Preserves any headers the raising code attached to the exception
        # — e.g. rate_limit.py's Retry-After — which would otherwise be
        # silently dropped by building a fresh JSONResponse here.
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = _current_request_id()
    logger.info("validation_error", extra={"request_id": request_id, "path": request.url.path})
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=_error_body("VALIDATION_ERROR", "The request was invalid.", request_id),
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    request_id = _current_request_id()
    # Full detail goes to the server log only — never to the client response.
    logger.error(
        "unhandled_exception",
        extra={"request_id": request_id, "path": request.url.path},
        exc_info=exc,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_error_body("INTERNAL_ERROR", "An unexpected error occurred.", request_id),
    )
