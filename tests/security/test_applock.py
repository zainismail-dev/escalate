"""The optional app lock (APP_PASSCODE): off by default, a session cookie when on."""

from collections.abc import Iterator

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from escalate.api.applock import COOKIE, FAILS_PER_CLIENT
from escalate.api.main import create_app
from escalate.config import get_settings
from tests.factories import APP_BASE_URL, APP_HEADERS

PASSCODE = "correct horse battery"


def _client(monkeypatch: pytest.MonkeyPatch, passcode: str | None) -> TestClient:
    if passcode is None:
        monkeypatch.delenv("APP_PASSCODE", raising=False)
    else:
        monkeypatch.setenv("APP_PASSCODE", passcode)
    get_settings.cache_clear()
    return TestClient(create_app(startup=False), base_url=APP_BASE_URL, headers=APP_HEADERS)


@pytest.fixture
def locked(monkeypatch: pytest.MonkeyPatch, db: Session) -> Iterator[TestClient]:
    with _client(monkeypatch, PASSCODE) as c:
        yield c
    get_settings.cache_clear()


def test_unset_passcode_changes_nothing(monkeypatch: pytest.MonkeyPatch, db: Session) -> None:
    with _client(monkeypatch, None) as c:
        assert c.get("/auth/status").json() == {"enabled": False, "unlocked": True}
        assert c.get("/cases").status_code == 200
        assert c.post("/auth/login", json={"passcode": "anything"}).status_code == 204
        assert COOKIE not in c.cookies
    get_settings.cache_clear()


def test_locked_until_the_right_passcode(locked: TestClient) -> None:
    assert locked.get("/cases").status_code == 401
    assert locked.get("/auth/status").json() == {"enabled": True, "unlocked": False}
    assert locked.post("/auth/login", json={"passcode": "wrong"}).status_code == 401
    assert locked.get("/cases").status_code == 401

    r = locked.post("/auth/login", json={"passcode": PASSCODE})
    assert r.status_code == 204
    cookie = r.headers["set-cookie"]
    assert f"{COOKIE}=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert "Path=/" in cookie
    assert "Secure" not in cookie  # plain http on localhost; https adds it
    assert locked.get("/cases").status_code == 200
    assert locked.get("/auth/status").json() == {"enabled": True, "unlocked": True}

    assert locked.post("/auth/logout").status_code == 204
    locked.cookies.clear()
    assert locked.get("/cases").status_code == 401


def test_logout_invalidates_the_token_server_side(locked: TestClient) -> None:
    locked.post("/auth/login", json={"passcode": PASSCODE})
    token = locked.cookies[COOKIE]
    locked.post("/auth/logout")
    locked.cookies.set(COOKIE, token)  # a copied cookie is no longer valid
    assert locked.get("/cases").status_code == 401


def test_forged_and_malformed_cookies_are_refused(locked: TestClient) -> None:
    for value in ("x", "a" * 43, '"; injected=1', ""):
        locked.cookies.set(COOKIE, value)
        assert locked.get("/cases").status_code == 401


def test_wrong_passcodes_are_rate_limited(locked: TestClient) -> None:
    for _ in range(FAILS_PER_CLIENT):
        assert locked.post("/auth/login", json={"passcode": "guess"}).status_code == 401
    r = locked.post("/auth/login", json={"passcode": PASSCODE})
    assert r.status_code == 429  # even the right one, until the backoff passes
    assert r.headers["retry-after"] == "30"


def test_login_is_behind_the_csrf_guard(locked: TestClient) -> None:
    r = locked.post(
        "/auth/login", json={"passcode": PASSCODE}, headers={"Origin": "https://evil.example"}
    )
    assert r.status_code == 403


def test_an_argon2_hash_works_as_the_passcode(monkeypatch: pytest.MonkeyPatch, db: Session) -> None:
    with _client(monkeypatch, PasswordHasher().hash(PASSCODE)) as c:
        assert c.post("/auth/login", json={"passcode": "nope"}).status_code == 401
        assert c.post("/auth/login", json={"passcode": PASSCODE}).status_code == 204
        assert c.get("/cases").status_code == 200
    get_settings.cache_clear()


def test_the_passcode_is_never_returned(locked: TestClient) -> None:
    locked.post("/auth/login", json={"passcode": PASSCODE})
    assert PASSCODE not in locked.get("/settings").text
    assert PASSCODE not in locked.get("/openapi.json").text


def test_parallel_guesses_cannot_exceed_the_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Second review N6: the limit was checked before the slow argon2 verify and recorded after
    it, so 40 parallel wrong logins were all verified. Attempts are now reserved first."""
    import threading

    from argon2.exceptions import VerifyMismatchError

    from escalate.api import applock

    monkeypatch.setenv("APP_PASSCODE", PASSCODE)
    get_settings.cache_clear()
    lock = applock.AppLock()
    lock._hash()  # hash once up front (outside the fake below)
    verified: list[int] = []
    release = threading.Event()
    done = threading.Condition()
    refused: list[int] = []

    class SlowWrongHasher:
        def verify(self, _hash: str, _pw: str) -> bool:
            verified.append(1)
            release.wait(10)  # every verify is in flight while the others arrive
            raise VerifyMismatchError

    monkeypatch.setattr(applock, "_hasher", SlowWrongHasher())

    def attempt() -> None:
        try:
            lock.login("guess", "203.0.113.9")
        except applock.TooManyAttempts:
            with done:
                refused.append(1)
                done.notify_all()

    threads = [threading.Thread(target=attempt) for _ in range(40)]
    for t in threads:
        t.start()
    with done:
        assert done.wait_for(lambda: len(refused) >= 35, timeout=10)
    release.set()
    for t in threads:
        t.join(10)
    get_settings.cache_clear()
    assert len(verified) <= applock.FAILS_PER_CLIENT
    assert len(refused) >= 35


def test_backoff_doubles_and_never_locks_out_other_clients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from freezegun import freeze_time

    from escalate.api import applock

    monkeypatch.setenv("APP_PASSCODE", PASSCODE)
    get_settings.cache_clear()
    lock = applock.AppLock()
    attacker = "203.0.113.9"
    with freeze_time("2026-10-29 12:00:00") as clock:
        for _ in range(applock.FAILS_PER_CLIENT):
            assert lock.login("guess", attacker) is None
        with pytest.raises(applock.TooManyAttempts) as first:
            lock.login("guess", attacker)
        assert first.value.retry_after == 30
        clock.tick(31)
        assert lock.login("guess", attacker) is None  # one more attempt, then 60 s
        with pytest.raises(applock.TooManyAttempts) as second:
            lock.login("guess", attacker)
        assert second.value.retry_after == 60
        # The owner on another address is never locked out by the flood.
        assert lock.login(PASSCODE, "127.0.0.1") is not None
    assert applock.backoff(30) == applock.BACKOFF_MAX
    get_settings.cache_clear()
