"""Endpoints the web app (web/) uses: countries, ladder and reasons, draft review, letter
language, settings, delete-all and demo data."""

import json
import stat
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from freezegun import freeze_time
from sqlalchemy import select

from escalate.agent.review import blanks, segments
from escalate.config import get_settings
from escalate.db.models import Message
from escalate.db.session import session_scope
from escalate.i18n.countries import currency_for, is_rtl, normalize_language
from escalate.i18n.formatting import locale_for
from escalate.playbooks.models import template_file
from tests.agent_env import AgentEnv, agent_env  # noqa: F401
from tests.fakes.fake_smtp import FakeSMTP
from tests.test_api import DAY0, _create, _started, client  # noqa: F401

WEB = "http://localhost:3000"


@pytest.fixture
def urdu_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """v0.1 ships English-only; tests of the dormant multi-language machinery turn Urdu on."""
    monkeypatch.setenv("ENABLED_LETTER_LANGUAGES", '["en","ur"]')
    get_settings.cache_clear()


def test_cors_allows_only_the_web_origin(client: TestClient) -> None:  # noqa: F811
    pre = {"Access-Control-Request-Method": "POST"}
    ok = client.options("/cases", headers={"Origin": WEB, **pre})
    assert ok.headers.get("access-control-allow-origin") == WEB
    other = client.options("/cases", headers={"Origin": "https://evil.example", **pre})
    assert "access-control-allow-origin" not in other.headers


def test_countries_cover_the_world_and_flag_local_packs(client: TestClient) -> None:  # noqa: F811
    rows = {c["code"]: c for c in client.get("/countries").json()}
    assert len(rows) > 240
    assert not {"EU", "ZZ", "UN", "QO"} & rows.keys()
    assert rows["PK"]["local_pack"] and rows["PK"]["currency"] == "PKR"
    assert "PK-SD" in rows["PK"]["regions"]
    assert rows["FR"]["local_pack"] is False and rows["FR"]["currency"] == "EUR"
    assert rows["FR"]["packs"] == {}


def test_language_tags_and_locales() -> None:
    assert normalize_language("ur_pk") == "ur-PK"
    assert normalize_language("PT-br") == "pt-BR"
    with pytest.raises(ValueError):
        normalize_language("english")
    assert is_rtl("ar") and is_rtl("ur-PK") and not is_rtl("en-GB")
    assert locale_for("en-GB", "PK") == "en_GB"
    assert locale_for("en", "PK") == "en_PK"
    assert currency_for("GB") == "GBP" and currency_for(None) is None
    p = template_file(Path("templates"), "pk/legal_notice_15_day.md.j2", "ur-PK")
    assert p is not None and p.parent.name == "ur"


def test_english_only_by_default(client: TestClient) -> None:  # noqa: F811
    case = _create(client)
    assert case["language"] == "en" and case["text_direction"] == "ltr"
    assert _create(client, language="en-GB")["language"] == "en-GB"  # English variants are fine
    for lang in ("ur", "fr-FR"):
        r = client.post("/cases", json={"description": "x" * 20, "language": lang})
        assert r.status_code == 422 and "not enabled" in r.text
    cid = case["id"]
    assert client.post(f"/cases/{cid}/letter-language", json={"language": "ur"}).status_code == 422
    assert client.put("/settings", json={"default_language": "ur"}).status_code == 422
    assert client.get("/settings").json()["enabled_letter_languages"] == ["en"]


def test_create_sets_currency_and_accepts_bcp47(
    client: TestClient,  # noqa: F811
    urdu_enabled: None,
) -> None:
    case = _create(client, language="ur-PK")
    assert case["language"] == "ur-PK" and case["currency"] == "PKR"
    assert case["text_direction"] == "rtl"
    bad = client.post("/cases", json={"description": "x" * 20, "language": "Urdu language"})
    assert bad.status_code == 422


def test_detail_has_ladder_and_reasons(client: TestClient) -> None:  # noqa: F811
    with freeze_time(DAY0):
        cid = _started(client)
        d = client.get(f"/cases/{cid}").json()
    states = [r["state"] for r in d["ladder"]]
    assert states[0] == "current" and set(states[1:]) <= {"future", "skipped"}
    codes = [r["code"] for r in d["reasons"]]
    assert codes[0] == "first_step" and "playbook" in codes and "wait" in codes
    pb = next(r for r in d["reasons"] if r["code"] == "playbook")["params"]
    assert pb["level"] == "region" and pb["playbook"] == "pk-ecommerce-refund-refused"
    assert d["waiting_for"] == "approve_draft" and d["sources"]
    row = client.get("/cases?country=pk").json()[0]
    assert row["waiting_for"] == "approve_draft" and len(row["ladder"]) == len(d["ladder"])
    assert client.get("/cases?q=nothing-like-this").json() == []


def test_review_highlights_facts_and_gates_blanks(client: TestClient) -> None:  # noqa: F811
    with freeze_time(DAY0):
        cid = _started(client)
        mid = client.get(f"/cases/{cid}").json()["pending_draft"]["id"]
        r = client.get(f"/messages/{mid}/review").json()
        facts = [s for s in r["body_segments"] if s["kind"] == "fact"]
        assert {"order_id", "amount"} <= {s["key"] for s in facts}
        assert any(s["text"].startswith("PKR") for s in facts)
        assert r["can_approve"] and all(c["ok"] for c in r["checks"])
        assert "ur" in r["template_languages"]

        body = r["message"]["body"].replace("Yours sincerely", "Phone: [[your phone]]\nYours")
        client.put(f"/messages/{mid}", json={"body": body})
        r = client.get(f"/messages/{mid}/review").json()
        assert r["blanks"] == ["your phone"] and not r["can_approve"]
        bad = client.post(f"/messages/{mid}/approve", json={})
        assert bad.status_code == 422 and "fill in the blank: your phone" in bad.json()["issues"]
        assert FakeSMTP.all_sent() == []


def test_review_shows_wrong_vs_evidence_value(client: TestClient) -> None:  # noqa: F811
    with freeze_time(DAY0):
        cid = _started(client)
        mid = client.get(f"/cases/{cid}").json()["pending_draft"]["id"]
        draft = client.get(f"/cases/{cid}").json()["pending_draft"]["body"]
        client.put(f"/messages/{mid}", json={"body": draft + "\nPay 77,777."})
        r = client.get(f"/messages/{mid}/review").json()
    assert not r["can_approve"]
    [p] = r["problems"]
    assert p["kind"] == "number" and p["wrong"] == "77777" and "amount" in p["expected"]


def test_preview_and_letter_language_switch(
    client: TestClient,  # noqa: F811
    urdu_enabled: None,
) -> None:
    with freeze_time(DAY0):
        cid = _started(client)
        mid = client.get(f"/cases/{cid}").json()["pending_draft"]["id"]
        ur = client.get(f"/messages/{mid}/preview?language=ur").json()
        assert ur["available"] and ur["text_direction"] == "rtl" and "BM-48213" in ur["body"]
        assert client.get(f"/messages/{mid}/preview?language=fr").status_code == 422  # not enabled
        assert client.get(f"/messages/{mid}/preview?language=x1").status_code == 422

        r = client.post(f"/cases/{cid}/letter-language", json={"language": "ur"}).json()
        assert r["waiting_for"] == "approve_draft"
        assert r["pending"]["draft"]["message_id"] != mid
        with session_scope() as s:
            old = s.get_one(Message, mid)
            assert old.status == "rejected" and old.approved_at is None
    assert FakeSMTP.all_sent() == []


def test_settings_round_trip_never_returns_secrets(
    client: TestClient,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "settings.json"
    monkeypatch.setenv("ESCALATE_SETTINGS_FILE", str(path))
    r = client.put(
        "/settings",
        json={
            "smtp_host": "smtp.example.org",
            "smtp_port": 587,
            "smtp_user": "me@example.org",
            "smtp_app_password": "abcd efgh",
            "default_country": "gb",
            "default_language": "en-gb",
        },
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["smtp_host"] == "smtp.example.org" and out["has_smtp_password"] is True
    assert out["default_country"] == "GB" and out["default_language"] == "en-GB"
    assert "abcd" not in r.text and "smtp_app_password" not in out
    assert json.loads(path.read_text())["smtp_port"] == 587
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert client.get("/settings").json()["smtp_user"] == "me@example.org"
    case = _create(client, country=None, region=None)
    assert case["country"] == "GB" and case["language"] == "en-GB"
    cleared = client.put("/settings", json={"smtp_app_password": ""}).json()
    assert cleared["has_smtp_password"] is False
    assert client.put("/settings", json={"llm_base_url": "ftp://x"}).status_code == 422


def test_delete_all(client: TestClient) -> None:  # noqa: F811
    with freeze_time(DAY0):
        _started(client)
        _create(client)
    assert client.post("/privacy/delete-all").status_code == 204
    assert client.get("/cases").json() == []


def test_demo_seed_runs_four_countries_and_sends_nothing(
    client: TestClient,  # noqa: F811
) -> None:
    with freeze_time(DAY0):
        ids = client.post("/demo/seed").json()["case_ids"]
        rows = {c["country"]: c for c in client.get("/cases").json()}
    assert len(ids) == 4 and set(rows) == {"PK", "IN", "GB", "US"}
    assert rows["IN"]["waiting_for"] == "urgent_checklist" and rows["IN"]["currency"] == "INR"
    assert rows["PK"]["waiting_for"] == "approve_draft" and rows["PK"]["amount"] == "64500.00"
    assert rows["GB"]["generic_playbook"] is True and rows["GB"]["language"] == "en"
    us = client.get(f"/cases/{rows['US']['id']}").json()
    review = client.get(f"/messages/{us['pending_draft']['id']}/review").json()
    assert review["blanks"] == ["your phone number"] and not review["can_approve"]
    pk = client.get(f"/cases/{rows['PK']['id']}").json()
    assert {f["source_evidence_id"] for f in pk["facts"]} == {pk["evidence"][0]["id"]}
    with session_scope() as s:
        assert s.scalars(select(Message).where(Message.sent_at.is_not(None))).all() == []
    assert FakeSMTP.all_sent() == []


def test_segments_prefer_longest_fact_and_keep_blanks() -> None:
    segs = segments(
        "Order BM-48213 for PKR 64,500.00. [[sign]]",
        {"order_id": ["BM-48213"], "amount": ["64500", "PKR 64,500.00"]},
    )
    kinds = [(s.kind, s.text) for s in segs if s.kind != "text"]
    assert kinds == [("fact", "BM-48213"), ("fact", "PKR 64,500.00"), ("blank", "[[sign]]")]
    assert blanks("a ____ b [[ x ]]") == ["____", "x"]


def test_override_verdict_replays_from_the_reply(client: TestClient) -> None:  # noqa: F811
    with freeze_time(DAY0):
        cid = _started(client)
        mid = client.get(f"/cases/{cid}").json()["pending_draft"]["id"]
        assert client.post(f"/messages/{mid}/approve", json={}).status_code == 200
        assert client.post(f"/cases/{cid}/verdict", json={"verdict": "resolved"}).status_code == 409
        r = client.post(f"/cases/{cid}/replies", json={"text": "We refuse."}).json()
        assert r["verdict"] == "refused" and r["waiting_for"] == "questions"
        assert "condition" in r and "promise_date" in r

        ok = client.post(f"/cases/{cid}/verdict", json={"verdict": "resolved"}).json()
        assert ok["waiting_for"] is None
        assert client.get(f"/cases/{cid}").json()["status"] == "resolved"

        back = client.post(f"/cases/{cid}/verdict", json={"verdict": "refused"}).json()
        assert back["waiting_for"] == "questions"
        types = [e["type"] for e in client.get(f"/cases/{cid}/timeline").json()]
        assert types.count("verdict_overridden") == 2
        assert client.post(f"/cases/{cid}/verdict", json={"verdict": "maybe"}).status_code == 422
    assert len(FakeSMTP.all_sent()) == 1  # only the approved letter
