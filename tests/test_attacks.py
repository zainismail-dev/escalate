"""Regression tests for the independent security review: each test replays an attack from the
report and checks it now fails. (Report: CSRF, DNS rebinding, SSRF, SMTP TLS, prompt
injection, information leaks.)"""

from collections.abc import Iterator
from typing import ClassVar

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


# --- 5. SSRF / secret redirection -------------------------------------------------------


@pytest.fixture
def settings_file(tmp_path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    from escalate.config import get_settings

    monkeypatch.setenv("ESCALATE_SETTINGS_FILE", str(tmp_path / "settings.json"))
    get_settings.cache_clear()
    yield tmp_path / "settings.json"
    get_settings.cache_clear()


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data",
        "http://[fd00:ec2::254]/",
        "http://[::ffff:169.254.169.254]/",
        "http://10.0.0.5:11434/v1",  # private but not listed as a local endpoint
        "file:///etc/passwd",
    ],
)
def test_settings_refuse_metadata_and_unlisted_private_urls(
    client: TestClient,  # noqa: F811
    settings_file: object,
    url: str,
) -> None:
    r = client.put("/settings", json={"llm_base_url": url})
    assert r.status_code == 422, r.text


def test_metadata_reached_through_dns_is_refused(
    client: TestClient,  # noqa: F811
    settings_file: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from escalate import netguard

    real = netguard.socket.getaddrinfo

    def fake_dns(host: str, *a: object, **kw: object) -> object:
        if host == "metadata.attacker.example":
            return [(2, 1, 6, "", ("169.254.169.254", 0))]
        return real(host, *a, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(netguard.socket, "getaddrinfo", fake_dns)
    r = client.put("/settings", json={"llm_base_url": "http://metadata.attacker.example/v1"})
    assert r.status_code == 422 and "metadata" in r.text
    assert (
        client.put("/settings", json={"smtp_host": "metadata.attacker.example"}).status_code == 422
    )


def test_local_endpoints_are_allowed_and_configurable(
    client: TestClient,  # noqa: F811
    settings_file: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from escalate.config import get_settings

    assert (
        client.put("/settings", json={"llm_base_url": "http://localhost:11434/v1"}).status_code
        == 200
    )
    monkeypatch.setenv("LOCAL_ENDPOINT_HOSTS", "localhost,10.0.0.5")
    get_settings.cache_clear()
    assert (
        client.put("/settings", json={"llm_base_url": "http://10.0.0.5:11434/v1"}).status_code
        == 200
    )


def test_changing_the_host_drops_the_stored_key(
    client: TestClient,  # noqa: F811
    settings_file: object,
) -> None:
    """Report #6 replay: after pointing LLM_BASE_URL at an internal listener, /settings/llm-test
    sent `Authorization: Bearer sk-victim` there. The key now stays with its original host."""
    import http.server
    import threading

    class Listener(http.server.BaseHTTPRequestHandler):
        seen: ClassVar[list[str | None]] = []

        def do_POST(self) -> None:
            Listener.seen.append(self.headers.get("Authorization"))
            self.send_response(500)
            self.end_headers()

        def log_message(self, *a: object) -> None:
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), Listener)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        ok = client.put(
            "/settings",
            json={"llm_base_url": "https://api.example.org/v1", "llm_api_key": "sk-victim"},
        )
        assert ok.json()["has_llm_api_key"] is True
        moved = client.put(
            "/settings",
            json={
                "llm_base_url": f"http://127.0.0.1:{srv.server_port}/internal",
                "model_fast": "m",
            },
        ).json()
        assert moved["cleared_secrets"] == ["llm_api_key"] and moved["has_llm_api_key"] is False
        client.post("/settings/llm-test")
        assert Listener.seen and all("sk-victim" not in (h or "") for h in Listener.seen)
    finally:
        srv.shutdown()
    smtp = client.put(
        "/settings", json={"smtp_host": "smtp.example.org", "smtp_app_password": "pw"}
    )
    assert smtp.json()["has_smtp_password"] is True
    moved_smtp = client.put("/settings", json={"smtp_host": "mail.example.net"}).json()
    assert moved_smtp["cleared_secrets"] == ["smtp_app_password"]
    assert moved_smtp["has_smtp_password"] is False


def test_unsafe_endpoints_from_env_are_refused_at_use_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A metadata URL set in .env (not via the API) is still never contacted."""
    from escalate.channels.email_smtp import SmtpChannel
    from escalate.config import Settings
    from escalate.db.models import Message
    from escalate.llm.client import LLMClient
    from escalate.netguard import UnsafeEndpoint

    bad = Settings(_env_file=None, llm_base_url="http://169.254.169.254/v1", model_smart="m")  # type: ignore[call-arg]
    with pytest.raises(UnsafeEndpoint):
        LLMClient(bad)

    def never(host: str, port: int) -> object:
        raise AssertionError("must not connect")

    s = Settings(_env_file=None, smtp_user="a@b.example", smtp_app_password="pw")  # type: ignore[call-arg]
    ch = SmtpChannel(s, smtp_factory=never, host="169.254.169.254")  # type: ignore[arg-type]
    msg = Message(
        id=1, recipient="x@y.example", subject="s", body="b", status="approved", approved_at=DAY0
    )
    with pytest.raises(UnsafeEndpoint):
        ch.send(msg, [])
