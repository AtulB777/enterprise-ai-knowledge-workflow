"""Standard security response headers (ADR-020) — genuinely absent from
this app before Phase 17, not just unverified. Most valuable for the HTML
FastAPI's own /docs (Swagger UI) serves, but applied to every response for
defense in depth regardless of content type.
"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        # This API is never meant to be framed — no
                        # legitimate use case for embedding it in an
                        # <iframe>, so DENY rather than SAMEORIGIN.
                        (b"x-frame-options", b"DENY"),
                        (b"referrer-policy", b"strict-origin-when-cross-origin"),
                        # No sniffable browser features this API needs.
                        (b"permissions-policy", b"geolocation=(), camera=(), microphone=()"),
                    ]
                )
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)
