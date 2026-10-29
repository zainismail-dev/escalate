"""Request guards for a single-user API without login (see SECURITY.md).

- CSRF: every state-changing request (POST, PUT, PATCH, DELETE) must come from an allowed
  Origin AND carry `X-Escalate-Request: 1`. A plain HTML form or `fetch(no-cors)` from another
  site cannot set a custom header, and setting one forces a CORS preflight that only the web
  app's origin passes.
- DNS rebinding: TrustedHostMiddleware (in main.py) rejects unknown Host headers.
"""

from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from fastapi.responses import JSONResponse

from escalate.config import Settings, get_settings

STATE_CHANGING = frozenset({"POST", "PUT", "PATCH", "DELETE"})
CSRF_HEADER = "X-Escalate-Request"

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def split_list(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def allowed_origins(settings: Settings | None = None) -> set[str]:
    """The web app (WEB_ORIGIN, also the CORS allow-list) and the Streamlit dev UI (UI_ORIGIN)."""
    s = settings or get_settings()
    return {o.rstrip("/") for o in [*split_list(s.web_origin), *split_list(s.ui_origin)]}


def csrf_problem(
    method: str, headers: dict[str, str], settings: Settings | None = None
) -> str | None:
    """Why a request must be refused, or None. Header names are lower-case."""
    if method not in STATE_CHANGING:
        return None
    origin = (headers.get("origin") or "").rstrip("/")
    if origin not in allowed_origins(settings):
        return "state-changing requests must come from the Escalate app (Origin not allowed)"
    if headers.get(CSRF_HEADER.lower()) != "1":
        return f"state-changing requests need the {CSRF_HEADER}: 1 header"
    return None


class CsrfGuard:
    """Pure ASGI middleware (runs before routing, so it also covers multipart uploads)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = {
                k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]
            }
            problem = csrf_problem(scope["method"], headers)
            if problem:
                await JSONResponse({"detail": problem}, status_code=403)(scope, receive, send)
                return
        await self.app(scope, receive, send)
