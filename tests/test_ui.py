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
    if path == "/settings":
        return {
            "ok": True,
            "is_cloud": True,
            "llm_base_url": "https://cloud",
            "demo_mode": False,
            "email_mode": "smtp",
            "version": "0.1.0",
        }
    if path == "/cases":
        return [CASE]
    if path == "/checklist":
        return {
            "country": "INTL",
            "items": [{"title": "Call your bank now", "detail": "x"}],
            "warnings": ["Never share OTPs"],
        }
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
    app.session_state["page"] = "new_case"
    app.run()
    assert not app.exception
    assert any("cloud" in w.value for w in app.warning)
    assert app.header[0].value == "What happened?"


def test_dashboard_shows_deadline_in_red(app: AppTest) -> None:
    app.session_state["page"] = "dashboard"
    app.run()
    assert not app.exception
    assert any("Deadline in 4 days" in e.value for e in app.error)


def test_review_page_shows_draft_and_facts(app: AppTest) -> None:
    app.session_state["page"] = "review"
    app.run()
    assert not app.exception
    assert app.text_area[0].value == "Dear seller"
    assert [b.label for b in app.button][:2] == ["Approve & send", "Save edit"]


def test_scam_page_shows_warnings_and_checklist(app: AppTest) -> None:
    app.session_state["page"] = "scam"
    app.run()
    assert not app.exception
    assert any("OTP" in w.value for w in app.warning)
    assert any("Call your bank now" in m.value for m in app.markdown)


def test_switching_ui_language_changes_labels(app: AppTest) -> None:
    app.session_state["page"] = "new_case"
    app.run()
    assert app.header[0].value == "What happened?"
    app.sidebar.selectbox[0].set_value("ur").run()
    assert not app.exception
    assert app.header[0].value == "کیا ہوا؟"
    # untranslated keys fall back to English
    assert app.text_area[0].label == "آپ کی کہانی"
    assert app.text_input[1].label.startswith("Province/state")


def test_every_ui_key_exists_in_english() -> None:
    import json
    import re

    from escalate.db.models import CaseStatus

    en = json.loads((UI.parent / "locales" / "en.json").read_text())
    source = (UI / "app.py").read_text()
    keys = {k for k in re.findall(r"""\bt\(\s*["']([\w.]+)["']""", source) if not k.endswith(".")}
    keys |= {
        f"page.{p}"
        for p in [
            "scam",
            "new_case",
            "cases",
            "dashboard",
            "questions",
            "review",
            "reply",
            "settings",
        ]
    }
    keys |= {f"verdict.{v}" for v in ["resolved", "partial", "refused", "no_reply"]}
    keys |= {f"status.{s.value}" for s in CaseStatus}  # built as t("status." + status)
    assert keys, "no t() calls found"
    assert sorted(keys - set(en)) == []


@pytest.mark.parametrize("page", ["cases", "questions", "reply", "settings"])
def test_other_pages_render(app: AppTest, page: str) -> None:
    app.session_state["page"] = page
    app.run()
    assert not app.exception


def test_settings_llm_test_button(app: AppTest, monkeypatch: pytest.MonkeyPatch) -> None:
    import api_client

    def fake_post(path: str, json: Any = None, files: Any = None) -> Any:
        return {"ok": False, "error": "LLMNotConfigured: set MODEL_SMART"}

    monkeypatch.setattr(api_client, "post", fake_post)
    app.session_state["page"] = "settings"
    app.run()
    app.button[0].click().run()
    assert any("MODEL_SMART" in e.value for e in app.error)
