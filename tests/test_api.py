from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from freezegun import freeze_time

from escalate.api.main import create_app
from escalate.config import get_settings
from tests.agent_env import AgentEnv, agent_env  # noqa: F401
from tests.factories import LED_TEXT
from tests.fakes.fake_smtp import FakeSMTP

FIX = Path(__file__).parent / "fixtures"
DAY0 = datetime(2026, 10, 1, 9, 0)


@pytest.fixture
def client(
    agent_env: AgentEnv,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[TestClient]:
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("EVIDENCE_DIR", str(tmp_path / "ev"))
    monkeypatch.setenv("LLM_BASE_URL", "https://api.example-cloud.com/v1")
    get_settings.cache_clear()
    with TestClient(create_app(startup=False)) as c:
        yield c
    get_settings.cache_clear()


def _create(client: TestClient, **kw: object) -> dict:
    body = {"description": LED_TEXT, "country": "PK", "region": "PK-SD", **kw}
    r = client.post("/cases", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_health_reports_cloud(client: TestClient) -> None:
    r = client.get("/health").json()
    assert r["ok"] and r["is_cloud"] is True


def test_create_validates_iso_codes(client: TestClient) -> None:
    bad = client.post("/cases", json={"description": LED_TEXT, "country": "Pakistan"})
    assert bad.status_code == 422
    wrong_region = client.post(
        "/cases", json={"description": LED_TEXT, "country": "PK", "region": "IN-MH"}
    )
    assert wrong_region.status_code == 422


def test_full_flow_over_http(client: TestClient) -> None:
    with freeze_time(DAY0):
        case = _create(client)
        cid = case["id"]
        assert case["status"] == "intake" and case["pending"] is None

        ev = client.post(
            f"/cases/{cid}/evidence",
            files={"file": ("receipt.pdf", (FIX / "receipt.pdf").read_bytes(), "application/pdf")},
        )
        assert ev.status_code == 201
        assert len(ev.json()["sha256"]) == 64

        r = client.post(f"/cases/{cid}/start").json()
        assert r["waiting_for"] == "approve_draft"
        assert client.post(f"/cases/{cid}/start").status_code == 409

        detail = client.get(f"/cases/{cid}").json()
        assert detail["playbook_id"] == "pk-ecommerce-refund-refused"
        assert {f["key"] for f in detail["facts"]} >= {"order_id", "amount"}
        draft = detail["pending_draft"]
        assert draft["status"] == "draft"
        mid = draft["id"]

        # edit: warnings for an invented amount, then approval is refused
        e = client.put(f"/messages/{mid}", json={"body": draft["body"] + "\nPay 77,777."})
        assert e.json()["warnings"] == ["number 77777 is not in the case facts"]
        bad = client.post(f"/messages/{mid}/approve", json={})
        assert bad.status_code == 422
        assert bad.json()["issues"] == ["number 77777 is not in the case facts"]
        assert FakeSMTP.all_sent() == []

        # fix the edit, approve -> sent
        client.put(f"/messages/{mid}", json={"body": draft["body"]})
        ok = client.post(f"/messages/{mid}/approve", json={})
        assert ok.status_code == 200, ok.text
        assert ok.json()["waiting_for"] == "waiting_reply"
        assert len(FakeSMTP.all_sent()) == 1
        assert client.post(f"/messages/{mid}/approve", json={}).status_code == 409

        listed = client.get("/cases").json()
        assert listed[0]["status"] == "waiting_reply"
        assert listed[0]["next_action_at"].startswith("2026-10-06")
        assert client.get("/cases?status=resolved").json() == []

        reply = client.post(
            f"/cases/{cid}/replies",
            json={"text": "We will replace when the company claim is approved."},
        ).json()
        assert reply["verdict"] == "refused"
        assert reply["waiting_for"] == "questions"

        types = [e["type"] for e in client.get(f"/cases/{cid}/timeline").json()]
        assert types.index("message_sent") < types.index("reply_judged")

        w = client.post(f"/cases/{cid}/withdraw", json={"reason": "done"})
        assert w.json()["status"] == "withdrawn"


def test_reject_over_http(client: TestClient) -> None:
    with freeze_time(DAY0):
        cid = _create(client, start=True)["id"]
        mid = client.get(f"/cases/{cid}").json()["pending_draft"]["id"]
        r = client.post(f"/messages/{mid}/reject", json={"reason": "too long"}).json()
        assert r["waiting_for"] == "approve_draft"
        assert r["pending"]["draft"]["message_id"] != mid


def test_answers_endpoint(client: TestClient, agent_env: AgentEnv) -> None:  # noqa: F811
    from tests.agent_env import make_llm

    agent_env.llm.rules[0] = ("You extract facts", make_llm({"buyer_name": "Ali"}).rules[0][1])
    with freeze_time(DAY0):
        cid = _create(client, start=True)["id"]
        detail = client.get(f"/cases/{cid}").json()
        assert detail["pending"]["type"] == "questions"
        assert client.post(f"/cases/{cid}/replies", json={"text": "x"}).status_code == 409


def test_upload_limit_and_404(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    cid = _create(client)["id"]
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    get_settings.cache_clear()
    big = client.post(f"/cases/{cid}/evidence", files={"file": ("a.txt", b"x" * (1024 * 1024 + 1))})
    assert big.status_code == 413
    assert client.get("/cases/999").status_code == 404


def test_export_not_ready_yet(client: TestClient) -> None:
    cid = _create(client)["id"]
    assert client.get(f"/cases/{cid}/export.pdf").status_code in (200, 501, 503)


def test_checklist_endpoint(client: TestClient) -> None:
    r = client.get("/checklist", params={"country": "ZZ"}).json()
    assert r["country"] == "INTL"
    assert any("OTP" in w for w in r["warnings"])
