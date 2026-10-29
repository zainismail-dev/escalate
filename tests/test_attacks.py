"""Regression tests for the independent security review: each test replays an attack from the
report and checks it now fails. (Report: CSRF, DNS rebinding, SSRF, SMTP TLS, prompt
injection, information leaks.)"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from freezegun import freeze_time

from escalate.api.main import create_app
from tests.agent_env import AgentEnv, agent_env  # noqa: F401
from tests.factories import APP_BASE_URL, APP_ORIGIN
from tests.fakes.fake_smtp import FakeSMTP
from tests.test_api import DAY0, _started, client  # noqa: F401

EVIL = "https://evil.example"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}


@pytest.fixture
def raw(client: TestClient) -> Iterator[TestClient]:  # noqa: F811
    """A client that sends only what each test adds (no Origin, no anti-CSRF header)."""
    with TestClient(create_app(startup=False), base_url=APP_BASE_URL) as c:
        yield c


def _draft(client: TestClient) -> tuple[str, str]:  # noqa: F811
    with freeze_time(DAY0):
        cid = _started(client)
    return cid, client.get(f"/cases/{cid}").json()["pending_draft"]["id"]


# --- 1. CSRF ---------------------------------------------------------------------------


def test_cross_site_form_cannot_approve_and_send(
    client: TestClient,  # noqa: F811
    raw: TestClient,
) -> None:
    """Report #1: an auto-submitting form on any site approved draft 1 and sent the email."""
    _, mid = _draft(client)
    attacks = [
        {"Origin": EVIL, **FORM},  # the original attack
        {"Origin": EVIL, "X-Escalate-Request": "1", "Content-Type": "application/json"},
        {"Origin": APP_ORIGIN, **FORM},  # right origin, no custom header (a form can't add one)
        {"X-Escalate-Request": "1", "Content-Type": "application/json"},  # no Origin
    ]
    for headers in attacks:
        r = raw.post(f"/messages/{mid}/approve", headers=headers, content=b'{"confirm": true}')
        assert r.status_code == 403, headers
    assert FakeSMTP.all_sent() == []
    # The real app still works, but only with an explicit confirmation body.
    assert client.post(f"/messages/{mid}/approve", content=b"").status_code == 422
    assert client.post(f"/messages/{mid}/approve", json={}).status_code == 422
    assert client.post(f"/messages/{mid}/approve", json={"confirm": True}).status_code == 200
    assert len(FakeSMTP.all_sent()) == 1


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/privacy/delete-all"),
        ("POST", "/demo/seed"),
        ("POST", "/settings/llm-test"),
        ("PUT", "/settings"),
        ("POST", "/cases/{cid}/start"),
        ("POST", "/cases/{cid}/retry"),
        ("POST", "/cases/{cid}/checklist/ack"),
        ("PATCH", "/cases/{cid}"),
        ("DELETE", "/cases/{cid}"),
        ("POST", "/messages/{mid}/reject"),
    ],
)
def test_every_state_change_needs_origin_and_header(
    client: TestClient,  # noqa: F811
    raw: TestClient,
    method: str,
    path: str,
) -> None:
    """Report #2: delete-all, start, retry, checklist ack, demo seed... worked cross-site."""
    cid, mid = _draft(client)
    url = path.format(cid=cid, mid=mid)
    r = raw.request(method, url, headers={"Origin": EVIL, **FORM}, content=b"")
    assert r.status_code == 403
    assert len(client.get("/cases").json()) == 1  # nothing deleted, nothing seeded


def test_cross_site_multipart_upload_is_refused(
    client: TestClient,  # noqa: F811
    raw: TestClient,
) -> None:
    cid, _ = _draft(client)
    files = {"file": ("note.txt", b"Seller email: refunds@attacker.example", "text/plain")}
    r = raw.post(f"/cases/{cid}/evidence", headers={"Origin": EVIL}, files=files)
    assert r.status_code == 403
    assert len(client.get(f"/cases/{cid}").json()["evidence"]) == 1


def test_delete_all_needs_a_confirmation_body(client: TestClient) -> None:  # noqa: F811
    _draft(client)
    assert client.post("/privacy/delete-all").status_code == 422
    assert client.post("/privacy/delete-all", json={"confirm": False}).status_code == 422
    assert len(client.get("/cases").json()) == 1


def test_reads_and_preflight_still_work(raw: TestClient) -> None:
    assert raw.get("/cases").status_code == 200  # reads are not CSRF-able state changes
    pre = raw.options(
        "/cases",
        headers={
            "Origin": APP_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-escalate-request",
        },
    )
    assert pre.status_code == 200
    assert "x-escalate-request" in pre.headers["access-control-allow-headers"].lower()


# --- 2. DNS rebinding --------------------------------------------------------------------


def test_unknown_host_header_is_refused(raw: TestClient) -> None:
    """Report #3: Host: rebind.attacker.example returned 200 with every case."""
    for host in ("attacker.example", "rebind.attacker.example"):
        assert raw.get("/cases", headers={"Host": host}).status_code == 400
    assert raw.get("/cases", headers={"Host": "localhost:8000"}).status_code == 200
    assert raw.get("/cases", headers={"Host": "127.0.0.1:8000"}).status_code == 200


def test_allowed_hosts_are_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    from escalate.config import get_settings

    monkeypatch.setenv("ALLOWED_HOSTS", "escalate.example.org")
    get_settings.cache_clear()
    try:
        with TestClient(create_app(startup=False), base_url="http://escalate.example.org") as c:
            assert c.get("/openapi.json").status_code == 200
            assert c.get("/openapi.json", headers={"Host": "localhost"}).status_code == 400
    finally:
        get_settings.cache_clear()
