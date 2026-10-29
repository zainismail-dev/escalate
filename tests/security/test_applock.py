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
    assert r.status_code == 429  # even the right one, until the window passes
    assert r.headers["retry-after"] == "900"


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
