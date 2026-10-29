import io
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from freezegun import freeze_time
from pypdf import PdfReader

from escalate.agent import runner
from escalate.db import session as db_session
from escalate.db.models import Case
from escalate.evidence.store import save_upload
from escalate.export.case_pdf import build_case_html, build_case_pdf
from escalate.export.pdf import pdf_available
from tests.agent_env import AgentEnv, agent_env, approve_pending, facts_reply  # noqa: F401
from tests.factories import LED_FACTS, LED_TEXT

FIX = Path(__file__).parent / "fixtures"
DAY0 = datetime(2026, 10, 1, 9, 0)


def _led_case_with_history(env: AgentEnv) -> int:
    with freeze_time(DAY0) as clock:
        cid = env.new_case(description=LED_TEXT, country="PK", region="PK-SD")
        with db_session.session_scope() as s:
            ev = save_upload(
                s, cid, "receipt.png", (FIX / "receipt.png").read_bytes(), env.settings
            )
            ev.extracted_text = "Order ID: BM-48213"  # what OCR reads, without Tesseract here
            ev_id = ev.id
        reply = facts_reply(LED_FACTS)
        reply["facts"]["order_id"]["evidence_id"] = ev_id  # the receipt is the source
        env.llm.rules[0] = ("You extract facts", reply)
        runner.start_case(cid)
        approve_pending(cid)
        clock.tick(timedelta(days=3))
        runner.resume_with_reply(cid, "We will replace it when the company claim is approved.")
    return cid


def _html(env: AgentEnv, cid: int, monkeypatch: pytest.MonkeyPatch) -> str:
    _use_settings(env, monkeypatch)
    with env.session() as s:
        case = s.get(Case, cid)
        assert case is not None
        return build_case_html(s, case)


def _use_settings(env: AgentEnv, monkeypatch: pytest.MonkeyPatch) -> None:
    from escalate.evidence import store

    monkeypatch.setattr(store, "get_settings", lambda: env.settings)


def test_case_html_has_every_section(agent_env: AgentEnv, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    env = agent_env
    cid = _led_case_with_history(env)
    html = _html(env, cid, monkeypatch)
    assert f"Case file #{cid}" in html
    assert "<h1>Refund refused by BrightMart Electronics</h1>" in html  # the case title
    assert "Ali Raza" in html and "BrightMart Electronics" in html
    assert "PKR 45,000.00" in html  # in the letter (ISO code, unambiguous)
    assert "<th>Amount</th><td>Rs\u00a045,000</td>" in html  # cover: format_amount
    assert "Facts and their sources" in html
    assert "evidence #1 (receipt.png)" in html
    assert "consumer's statement" in html  # facts from the user's own words
    assert "Refund" in html or "BM-48213" in html  # the sent message
    assert "We will replace it when the company claim is approved." in html
    assert "data:image/jpeg;base64," in html  # receipt thumbnail
    assert "not legal advice" in html
    with env.session() as s:
        case = s.get(Case, cid)
        assert case is not None
        for ev in case.events:
            assert ev.created_at.strftime("%Y-%m-%d %H:%M") in html
        assert case.evidence[0].sha256 in html


def test_case_html_escapes_user_text(agent_env: AgentEnv, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    env = agent_env
    cid = env.new_case(description="<script>alert(1)</script> my order failed", country="PK")
    html = _html(env, cid, monkeypatch)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


@pytest.mark.skipif(not pdf_available(), reason="WeasyPrint system libraries not installed")
def test_pdf_builds_with_case_number_and_event_dates(
    agent_env: AgentEnv,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = agent_env
    cid = _led_case_with_history(env)
    _use_settings(env, monkeypatch)
    with env.session() as s:
        case = s.get(Case, cid)
        assert case is not None
        pdf = build_case_pdf(s, case)
        dates = {ev.created_at.strftime("%Y-%m-%d") for ev in case.events}
    assert pdf.startswith(b"%PDF")
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
    assert f"Case file #{cid}" in text
    for d in dates:
        assert d in text
