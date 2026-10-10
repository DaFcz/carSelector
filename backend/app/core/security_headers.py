"""Security response headers for every HTTP response - the REST API and
the NiceGUI UI alike (it is mounted on the same app, see `app/main.py`).

The Content-Security-Policy deliberately leaves scripts and styles alone:
NiceGUI renders with inline scripts and runtime-compiled Vue templates, so
a script-restricting policy would break the UI. It covers what doesn't
depend on that - who may frame the pages (clickjacking), plugins, `<base>`
hijacking, and where forms may post (article HTML is author-written).
"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core import config

CONTENT_SECURITY_POLICY = "frame-ancestors 'self'; object-src 'none'; base-uri 'self'; form-action 'self'"

# One year; sent only when the app is served over HTTPS (see
# `SESSION_COOKIE_HTTPS_ONLY`) - over plain HTTP browsers ignore it anyway,
# and a localhost run must never pin itself to HTTPS.
_HSTS = "max-age=31536000"


def security_headers() -> list[tuple[bytes, bytes]]:
    """The headers to add, as raw ASGI header pairs.

    Returns:
        `(name, value)` pairs, lowercase names.
    """
    headers = {
        "content-security-policy": CONTENT_SECURITY_POLICY,
        "x-frame-options": "SAMEORIGIN",  # frame-ancestors for older browsers
        "x-content-type-options": "nosniff",
        # Shared links carry their token in the path (/s/<token>) - never
        # send the full URL to other sites.
        "referrer-policy": "strict-origin-when-cross-origin",
        "permissions-policy": "camera=(), microphone=(), geolocation=()",
    }
    if config.SESSION_COOKIE_HTTPS_ONLY:
        headers["strict-transport-security"] = _HSTS
    return [(name.encode(), value.encode()) for name, value in headers.items()]


class SecurityHeadersMiddleware:
    """Pure ASGI middleware (not Starlette's `BaseHTTPMiddleware`, which
    buffers streaming responses) that adds `security_headers()` to every
    HTTP response, keeping any header a route already set. Websocket and
    lifespan traffic passes through untouched.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Args:
        app: The wrapped ASGI app.
        """
        self.app = app
        self._headers = security_headers()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                existing = {name.lower() for name, _ in message.get("headers", [])}
                extra = [(name, value) for name, value in self._headers if name not in existing]
                message = {**message, "headers": [*message.get("headers", []), *extra]}
            await send(message)

        await self.app(scope, receive, send_with_headers)
