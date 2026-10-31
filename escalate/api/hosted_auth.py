"""Hosted mode: every request carries a Supabase access token (`Authorization: Bearer ...`).

Pure ASGI, like the other guards, so it runs before routing and before any body is read. Only
GET /health and /internal/* (which has its own secret) are open; everything else without a
valid token is a 401. A valid token makes its user current for the request
(escalate/db/tenancy.py) and is available to routes as `request.state.identity`.
"""

import json
import logging
from functools import partial

import anyio

from escalate.api.security import ASGIApp, Receive, Scope, Send
from escalate.config import get_settings
from escalate.db.tenancy import as_user
from escalate.hosted.jwt import AuthError, Identity, Jwks, verify

OPEN_PATHS = frozenset({"/health"})
INTERNAL_PREFIX = "/internal/"

log = logging.getLogger("uvicorn.error")


def bearer(scope: Scope) -> str | None:
    for k, v in scope["headers"]:
        if k.lower() == b"authorization":
            scheme, _, token = v.decode("latin-1").partition(" ")
            if scheme.lower() != "bearer" or not token.strip():
                return None
            return token.strip()
    return None


async def _unauthorized(send: Send) -> None:
    body = json.dumps({"detail": "sign in required", "signed_in": False}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"www-authenticate", b"Bearer"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class HostedAuth:
    def __init__(self, app: ASGIApp, jwks: Jwks | None = None) -> None:
        self.app = app
        s = get_settings()
        self.jwks = jwks or Jwks(s.jwks_url, s.supabase_jwt_alg, s.jwks_cache_seconds)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or path in OPEN_PATHS or path.startswith(INTERNAL_PREFIX):
            await self.app(scope, receive, send)
            return
        identity = await self.identity(scope)
        if identity is None:
            await _unauthorized(send)
            return
        scope.setdefault("state", {})["identity"] = identity
        with as_user(identity.user_id):  # copied into the threads that run the route
            await self.app(scope, receive, send)

    async def identity(self, scope: Scope) -> Identity | None:
        token = bearer(scope)
        if token is None or len(token) > 8192:
            return None
        try:
            # A JWKS refresh is a network call: off the event loop.
            return await anyio.to_thread.run_sync(partial(verify, token, get_settings(), self.jwks))
        except AuthError as exc:
            log.info("refused a token: %s", exc)
            return None
