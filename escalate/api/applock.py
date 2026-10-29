"""Optional app lock: set APP_PASSCODE and every route except the few below needs a session.

Not user accounts (v0.1 is single-user, see SECURITY.md): a passcode that keeps someone else on
the same computer or network out. Unset = no lock and no change in behaviour.

- APP_PASSCODE may be plain text or an argon2 hash (`python -m escalate.api.applock hash`); a
  plain value is hashed in memory at first use, so it is only ever compared with argon2.
- A correct passcode sets an httpOnly, SameSite=Strict session cookie (Secure over https).
  Sessions live in memory: restarting the API locks the app again.
- Failed attempts are rate limited per client and in total.
"""

import secrets
import sys
import threading
import time
from collections import deque
from collections.abc import Iterable
from http.cookies import SimpleCookie

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from escalate.api.security import ASGIApp, Receive, Scope, Send
from escalate.config import get_settings

COOKIE = "escalate_session"
# Reachable without a session: liveness, the lock screen's own calls, and CORS preflights.
OPEN_ROUTES = frozenset(
    {("GET", "/health"), ("GET", "/auth/status"), ("POST", "/auth/login"), ("POST", "/auth/logout")}
)
FAIL_WINDOW = 15 * 60  # seconds
FAILS_PER_CLIENT = 5
FAILS_TOTAL = 20

_hasher = PasswordHasher()


class TooManyAttempts(Exception):
    pass


class AppLock:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, float] = {}  # token -> expiry (epoch seconds)
        self._fails: dict[str, deque[float]] = {}
        self._hashes: dict[str, str] = {}  # configured passcode -> argon2 hash

    @staticmethod
    def enabled() -> bool:
        return bool(get_settings().app_passcode)

    def _hash(self) -> str:
        configured = get_settings().app_passcode
        if configured.startswith("$argon2"):
            return configured
        if configured not in self._hashes:
            self._hashes = {configured: _hasher.hash(configured)}
        return self._hashes[configured]

    def _recent_fails(self, key: str, now: float) -> deque[float]:
        fails = self._fails.setdefault(key, deque())
        while fails and fails[0] <= now - FAIL_WINDOW:
            fails.popleft()
        return fails

    def login(self, passcode: str, client: str) -> str | None:
        """A new session token, or None for a wrong passcode. Raises TooManyAttempts."""
        now = time.time()
        with self._lock:
            mine, total = self._recent_fails(client, now), self._recent_fails("*", now)
            if len(mine) >= FAILS_PER_CLIENT or len(total) >= FAILS_TOTAL:
                raise TooManyAttempts(
                    f"too many wrong passcodes; try again in {FAIL_WINDOW // 60} minutes"
                )
        ok: bool
        try:
            ok = _hasher.verify(self._hash(), passcode)
        except (VerificationError, InvalidHashError):
            ok = False
        with self._lock:
            if not ok:
                mine.append(now)
                total.append(now)
                return None
            token = secrets.token_urlsafe(32)
            self._sessions[token] = now + get_settings().app_session_hours * 3600
            return token

    def valid(self, token: str | None) -> bool:
        if not token:
            return False
        with self._lock:
            expiry = self._sessions.get(token)
            if expiry is None:
                return False
            if expiry <= time.time():
                del self._sessions[token]
                return False
            return True

    def logout(self, token: str | None) -> None:
        with self._lock:
            self._sessions.pop(token or "", None)


def session_token(headers: Iterable[tuple[bytes, bytes]]) -> str | None:
    for key, value in headers:
        if key.lower() == b"cookie":
            jar: SimpleCookie = SimpleCookie()
            try:
                jar.load(value.decode("latin-1"))
            except Exception:  # nosec B112
                continue  # a malformed Cookie header is just "no session"
            if COOKIE in jar:
                return jar[COOKIE].value
    return None


class AppLockGuard:
    """Pure ASGI: refuses every non-open route without a valid session when the lock is on."""

    def __init__(self, app: ASGIApp, lock: AppLock) -> None:
        self.app = app
        self.lock = lock

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or not self.lock.enabled()
            or scope["method"] == "OPTIONS"
            or (scope["method"], scope["path"]) in OPEN_ROUTES
            or self.lock.valid(session_token(scope["headers"]))
        ):
            await self.app(scope, receive, send)
            return
        body = b'{"detail":"Escalate is locked: enter your passcode","locked":true}'
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def main(argv: list[str]) -> int:
    """`python -m escalate.api.applock hash`: print an argon2 hash to put in APP_PASSCODE."""
    if argv[1:] != ["hash"]:
        print("usage: python -m escalate.api.applock hash", file=sys.stderr)
        return 2
    import getpass

    first = getpass.getpass("Passcode: ")
    if len(first) < 8:
        print("use at least 8 characters", file=sys.stderr)
        return 1
    if getpass.getpass("Again: ") != first:
        print("the two passcodes differ", file=sys.stderr)
        return 1
    print(_hasher.hash(first))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
