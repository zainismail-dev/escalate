"""Optional app lock: set APP_PASSCODE and every route except the few below needs a session.

Not user accounts (v0.1 is single-user, see SECURITY.md): a passcode that keeps someone else on
the same computer or network out. Unset = no lock and no change in behaviour.

- APP_PASSCODE may be plain text or an argon2 hash (`python -m escalate.api.applock hash`); a
  plain value is hashed in memory at first use, so it is only ever compared with argon2.
- A correct passcode sets an httpOnly, SameSite=Strict session cookie (Secure over https).
  Sessions live in memory: restarting the API locks the app again.
- Each check of a passcode is reserved first (no parallel guessing). Per client: 5 free
  attempts, then one at a time with exponential backoff (30 s doubling, 15 min cap).
"""

import secrets
import sys
import threading
import time
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
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
FAIL_WINDOW = 15 * 60  # seconds: failures older than this are forgotten
FAILS_PER_CLIENT = 5  # free attempts; after that one at a time, with exponential backoff
BACKOFF_START = 30  # seconds after the 5th failure, doubling with each further failure
BACKOFF_MAX = 15 * 60

_hasher = PasswordHasher()


class TooManyAttempts(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__(f"too many wrong passcodes; try again in {retry_after} seconds")
        self.retry_after = retry_after


@dataclass
class _Client:
    fails: deque[float] = field(default_factory=deque)
    in_flight: int = 0  # attempts reserved and being verified right now
    blocked_until: float = 0.0


def backoff(fails: int) -> float:
    """Seconds to wait after `fails` recent failures (0 while under the free attempts)."""
    if fails < FAILS_PER_CLIENT:
        return 0.0
    return float(min(BACKOFF_MAX, BACKOFF_START * 2 ** (fails - FAILS_PER_CLIENT)))


class AppLock:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, float] = {}  # token -> expiry (epoch seconds)
        self._clients: dict[str, _Client] = {}
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

    def _reserve(self, client: str, now: float) -> _Client:
        """Atomically claim one attempt before the (slow) argon2 check, so parallel requests
        can't all pass the limit check first. Limits are per client: a flood from one address
        never locks the owner out from another."""
        with self._lock:
            st = self._clients.setdefault(client, _Client())
            while st.fails and st.fails[0] <= now - FAIL_WINDOW:
                st.fails.popleft()
            used = len(st.fails) + st.in_flight
            over = len(st.fails) >= FAILS_PER_CLIENT
            if now < st.blocked_until or (used >= FAILS_PER_CLIENT and (not over or st.in_flight)):
                wait = max(st.blocked_until - now, 1.0)
                raise TooManyAttempts(int(wait + 0.999))
            st.in_flight += 1
            return st

    def login(self, passcode: str, client: str) -> str | None:
        """A new session token, or None for a wrong passcode. Raises TooManyAttempts."""
        now = time.time()
        st = self._reserve(client, now)
        ok: bool
        try:
            ok = _hasher.verify(self._hash(), passcode)
        except (VerificationError, InvalidHashError):
            ok = False
        finally:
            with self._lock:
                st.in_flight -= 1
        with self._lock:
            if not ok:
                st.fails.append(now)
                st.blocked_until = now + backoff(len(st.fails))
                return None
            st.fails.clear()
            st.blocked_until = 0.0
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
