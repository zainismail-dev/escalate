"""Smoke tests for the Streamlit UI with a fake API (no server, no network)."""

import sys
from pathlib import Path
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

UI = Path(__file__).resolve().parents[1] / "ui"

CASE = {
    "id": 1,
    "status": "awaiting_approval",
    "company": "BrightMart",
    "step_name": "written demand",
    "next_action_at": None,
    "deadlines": [
        {
            "id": "court_filing_limit",
            "rule": "30 days",
            "due": "2026-11-01",
            "days_left": 4,
            "warn": True,
            "late": False,
        }
    ],
    "generic_playbook": False,
    "facts": [{"key": "order_id", "value": "BM-48213"}],
    "pending": {"type": "approve_draft", "draft": {"message_id": 5}},
    "pending_draft": {
        "id": 5,
        "subject": "Refund",
        "body": "Dear seller",
        "recipient": "a@b.c",
        "channel": "email",
    },
}


def fake_get(path: str, **params: Any) -> Any:
    if path == "/health":
        return {"ok": True, "is_cloud": True, "llm_base_url": "https://cloud", "demo_mode": False}
    if path == "/cases":
        return [CASE]
    if path == "/cases/1/timeline":
        return [{"created_at": "2026-10-01T09:00:00", "type": "draft_created"}]
    return CASE


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> AppTest:
    monkeypatch.syspath_prepend(str(UI))
    sys.modules.pop("api_client", None)
    import api_client

    monkeypatch.setattr(api_client, "get", fake_get)
    return AppTest.from_file(str(UI / "app.py"), default_timeout=30)


def test_new_case_page_renders_with_privacy_banner(app: AppTest) -> None:
    app.run()
    assert not app.exception
    assert any("cloud" in w.value for w in app.warning)
    assert app.header[0].value == "What happened?"


def test_dashboard_shows_deadline_in_red(app: AppTest) -> None:
    app.session_state["page"] = "Case dashboard"
    app.run()
    assert not app.exception
    assert any("Deadline in 4 days" in e.value for e in app.error)


def test_review_page_shows_draft_and_facts(app: AppTest) -> None:
    app.session_state["page"] = "Review draft"
    app.run()
    assert not app.exception
    assert app.text_area[0].value == "Dear seller"
    assert [b.label for b in app.button][:2] == ["Approve & send", "Save edit"]
