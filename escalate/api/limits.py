"""Request limits: per-client rate limits on writes and AI calls, and a request body cap.

Pure ASGI (like CsrfGuard) so it runs before routing and before any body is parsed. Limits are
per client address, in memory (one API process). They protect a single user's machine from a
runaway script or a page that loops, and an AI endpoint that costs money from being hammered.
"""

import json
import re
from collections.abc import MutableMapping
from datetime import timedelta
from typing import Any

from escalate.api.security import STATE_CHANGING, ASGIApp, Receive, Scope, Send
from escalate.config import get_settings
from escalate.safety import RateLimited, RateLimiter

MINUTE = timedelta(minutes=1)

# State-changing routes that run the agent (and so the LLM). Everything else state-changing is a
# plain write.
AI_PATHS = re.compile(
    r"^/(cases/[^/]+/(start|answers|checklist/ack|retry|replies|resolution|verdict|letter-language)"
    r"|messages/[^/]+/(approve|reject|confirm-delivery)"
    r"|settings/llm-test)$"
)


async def _reply(send: Send, status: int, detail: str, headers: list[tuple[bytes, bytes]]) -> None:
    body = json.dumps({"detail": detail}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                *headers,
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


def body_limit(headers: dict[str, str]) -> int:
    s = get_settings()
    if headers.get("content-type", "").startswith("multipart/form-data"):
        return (s.upload_limit_mb + 1) * 1024 * 1024  # +1 MB for the multipart envelope
    return s.max_json_body_kb * 1024


class RequestLimits:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.limiter = RateLimiter()  # per app: a fresh app (and test client) starts at zero

    def rate_problem(self, method: str, path: str, client: str) -> str | None:
        if method not in STATE_CHANGING:
            return None
        s = get_settings()
        ai = bool(AI_PATHS.match(path))
        bucket, limit = (
            ("ai", s.rate_limit_ai_per_minute) if ai else ("write", s.rate_limit_writes_per_minute)
        )
        try:
            what = "AI requests" if ai else "changes"
            self.limiter.check(f"{bucket}:{client}", limit, MINUTE, what=what)
        except RateLimited as exc:
            return str(exc)
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        client = (scope.get("client") or ("unknown", 0))[0]
        problem = self.rate_problem(scope["method"], scope["path"], client)
        if problem:
            await _reply(send, 429, problem, [(b"retry-after", b"60")])
            return

        limit = body_limit(headers)
        too_big = f"request body is larger than {limit // 1024} KB"
        declared = headers.get("content-length", "")
        if declared.isdigit() and int(declared) > limit:
            await _reply(send, 413, too_big, [])
            return

        received = 0
        started = False
        refused = False

        async def counted_receive() -> MutableMapping[str, Any]:
            nonlocal received, refused
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    # Answer 413 now and tell the app the client left, so it stops reading.
                    if not started and not refused:
                        refused = True
                        await _reply(send, 413, too_big, [])
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: MutableMapping[str, Any]) -> None:
            nonlocal started
            if refused:
                return  # the 413 already went out
            started = started or message["type"] == "http.response.start"
            await send(message)

        await self.app(scope, counted_receive, guarded_send)
