"""Safety audit (task 4.2): one test per item."""

import ast
import logging
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from freezegun import freeze_time
from sqlalchemy import select
from sqlalchemy.orm import Session

from escalate.agent import runner
from escalate.agent.draft import draft_step
from escalate.agent.fact_check import code_check
from escalate.api.main import create_app
from escalate.channels import get_channel, send_message
from escalate.config import get_settings
from escalate.db import session as db_session
from escalate.db.events import log_event
from escalate.db.models import Case, CaseFact, Event, Evidence, Message
from escalate.evidence.store import save_upload
from escalate.pii import PiiFilter, mask_pii
from escalate.playbooks.loader import get_playbook
from escalate.safety import HarassmentPattern, new_case_limiter
from escalate.scheduler import jobs
from tests.agent_env import AgentEnv, agent_env, approve_pending  # noqa: F401
from tests.factories import (
    APP_BASE_URL,
    APP_HEADERS,
    LED_FACTS,
    LED_TEXT,
    approve_as_user,
    led_case,
)
from tests.fakes.fake_smtp import FakeSMTP

ROOT = Path(__file__).resolve().parents[2] / "escalate"
DAY0 = datetime(2026, 10, 1, 9, 0)
CARD = "4111 1111 1111 1111"


# --- 1. every path that could send goes through require_approval ----------------------


def _calls(tree: ast.AST) -> list[str]:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            out.append(f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", ""))
    return out


def test_only_email_channels_touch_the_network() -> None:
    allowed = {"channels/email_smtp.py", "channels/email_gmail.py"}
    for path in ROOT.rglob("*.py"):
        rel = str(path.relative_to(ROOT))
        src = path.read_text()
        if "smtplib" in src or "googleapiclient" in src or ".messages().send" in src:
            assert rel in allowed, f"{rel} can send email"


def _is_doc(st: ast.stmt) -> bool:
    return isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant)


def test_every_channel_send_starts_with_require_approval() -> None:
    found = 0
    for path in (ROOT / "channels").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.ClassDef):
                continue
            for fn in node.body:
                if not (isinstance(fn, ast.FunctionDef) and fn.name == "send"):
                    continue
                body = [st for st in fn.body if not _is_doc(st)]
                if not body:
                    continue  # the Channel Protocol stub (`...`)
                found += 1
                assert "require_approval" in _calls(body[0]), f"{path.name}:{node.name}"
    assert found >= 6


def test_registry_checks_approval_before_any_channel() -> None:
    tree = ast.parse((ROOT / "channels" / "__init__.py").read_text())
    fns = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    for name in ("send_message", "confirm_delivery"):
        calls = _calls(fns[name])
        assert "require_approval" in calls, name


def test_llm_gets_no_tools() -> None:
    for path in (ROOT / "llm").rglob("*.py"):
        src = path.read_text()
        assert "tools=" not in src and "functions=" not in src, path


# --- 2. PII masking -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "hidden", "kept"),
    [
        (f"card {CARD}", "4111 1111 1111 1111", "1111"),
        ("IBAN PK36SCBL0000001123456702", "SCBL0000001123", "6702"),
        ("CNIC 42101-1234567-1", "42101-1234567", "5671"),
        ("Aadhaar 1234 5678 9012", "1234 5678", "9012"),
        ("SSN 123-45-6789", "123-45", "6789"),
        ("NI AB 12 34 56 C", "AB 12 34", "456C"),
        ("my OTP is 482913", "482913", "OTP"),
        ("password: hunter2", "hunter2", "password"),
    ],
)
def test_mask_pii(raw: str, hidden: str, kept: str) -> None:
    out = mask_pii(raw)
    assert hidden not in out and kept in out


@pytest.mark.parametrize(
    "safe", ["order BM-48213 on 2026-02-14", "tracking 7731990", "4111 1111 1111 1112", "pinned"]
)
def test_mask_pii_leaves_normal_values(safe: str) -> None:
    assert mask_pii(safe) == safe


def test_logs_are_masked(caplog: pytest.LogCaptureFixture) -> None:
    log = logging.getLogger("escalate.test")
    log.addFilter(PiiFilter())
    with caplog.at_level(logging.INFO):
        log.info("user paid with %s", CARD)
    assert CARD not in caplog.text and "1111" in caplog.text


def test_events_case_text_and_drafts_are_masked(db: Session) -> None:
    case = led_case(db)
    db.add(CaseFact(case_id=case.id, key="return_tracking", value=f"card {CARD}"))
    db.flush()
    db.refresh(case)
    ev = log_event(db, case.id, "note", {"text": f"card {CARD}", "nested": ["OTP 123456"]})
    assert CARD not in str(ev.payload) and "123456" not in str(ev.payload)
    pb = get_playbook("intl-generic-refund-refused")
    msg = draft_step(db, case, pb, pb.steps[0], use_llm=False)
    assert CARD not in msg.body and "•••• 1111" in msg.body
    # a masked value is still a known fact for the fact check
    assert code_check(msg.body, case.fact_dict()) == [] or all(
        i.startswith("date") for i in code_check(msg.body, case.fact_dict())
    )


def test_evidence_text_is_masked(db: Session, settings: object) -> None:
    case = led_case(db)
    ev = save_upload(db, case.id, "note.txt", f"paid with {CARD}".encode(), settings)  # type: ignore[arg-type]
    assert CARD not in (ev.extracted_text or "")


# --- 3. one-click deletion --------------------------------------------------------------


def test_delete_case_removes_rows_files_jobs_and_checkpoint(
    agent_env: AgentEnv,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from escalate.evidence import store

    env = agent_env
    monkeypatch.setattr(store, "get_settings", lambda: env.settings)
    with freeze_time(DAY0):
        cid = env.new_case(description=LED_TEXT, country="PK", region="PK-SD")
        with db_session.session_scope() as s:
            ev = save_upload(s, cid, "r.txt", b"receipt BM-48213", env.settings)
            path = Path(ev.file_path)
        runner.start_case(cid)
        approve_pending(cid)
        assert env.scheduler.get_jobs() and path.exists()

        runner.delete_case(cid)

    assert env.scheduler.get_jobs() == []
    assert not path.exists() and not path.parent.exists()
    assert runner.pending(cid) is None
    with env.session() as s:
        for model in (Case, CaseFact, Evidence, Message, Event):
            assert s.scalars(select(model)).all() == []


# --- 4. rate limit, evidence required, harassment pattern -------------------------------


@pytest.fixture
def api(
    agent_env: AgentEnv,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[TestClient]:
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("EVIDENCE_DIR", str(tmp_path / "ev"))
    monkeypatch.setenv("MAX_NEW_CASES_PER_HOUR", "3")
    get_settings.cache_clear()
    new_case_limiter.reset()
    with TestClient(create_app(startup=False), base_url=APP_BASE_URL, headers=APP_HEADERS) as c:
        yield c
    get_settings.cache_clear()


def test_new_cases_are_rate_limited(api: TestClient) -> None:
    body = {"description": LED_TEXT, "country": "PK"}
    with freeze_time(DAY0) as clock:
        codes = [api.post("/cases", json=body).status_code for _ in range(4)]
        assert codes == [201, 201, 201, 429]
        clock.tick(timedelta(hours=1, seconds=1))
        assert api.post("/cases", json=body).status_code == 201


def test_case_without_evidence_cannot_start(api: TestClient) -> None:
    cid = api.post("/cases", json={"description": LED_TEXT, "country": "PK"}).json()["id"]
    r = api.post(f"/cases/{cid}/start")
    assert r.status_code == 422 and "evidence" in r.json()["detail"]


def test_one_click_delete_endpoint(api: TestClient) -> None:
    cid = api.post("/cases", json={"description": LED_TEXT, "country": "PK"}).json()["id"]
    assert api.delete(f"/cases/{cid}").status_code == 204
    assert api.get(f"/cases/{cid}").status_code == 404


def test_repeated_recipient_is_refused(db: Session) -> None:
    pb = get_playbook("intl-generic-refund-refused")
    for _ in range(3):
        case = led_case(db)
        approve_as_user(db, draft_step(db, case, pb, pb.steps[0], use_llm=False).id)
    fourth = led_case(db)
    msg = draft_step(db, fourth, pb, pb.steps[0], use_llm=False)
    with pytest.raises(HarassmentPattern):
        approve_as_user(db, msg.id)
    assert msg.approved_at is None


def test_same_case_can_write_to_its_recipient_repeatedly(db: Session) -> None:
    pb = get_playbook("intl-generic-refund-refused")
    case = led_case(db)
    for step in pb.steps[:2]:
        approve_as_user(db, draft_step(db, case, pb, step, use_llm=False).id)


# --- 5. DEMO_MODE ---------------------------------------------------------------------


@pytest.fixture
def demo(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("DEMO_MODE", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_demo_mode_never_sends_real_email(agent_env: AgentEnv, demo: None) -> None:  # noqa: F811
    assert type(get_channel("email")).__name__ == "DemoEmailChannel"
    with freeze_time(DAY0):
        cid = agent_env.new_case(description=LED_TEXT, country="PK", region="PK-SD")
        runner.start_case(cid)
        r = approve_pending(cid)
    assert r.waiting_for == "waiting_reply"
    assert FakeSMTP.all_sent() == []  # the fake SMTP override is ignored too
    with agent_env.session() as s:
        msg = s.scalars(select(Message).where(Message.case_id == cid)).first()
        assert msg is not None and msg.external_id == f"demo-{msg.id}"


def test_demo_mode_still_needs_approval(db: Session, demo: None) -> None:
    from escalate.channels import NotApproved

    case = led_case(db)
    pb = get_playbook("intl-generic-refund-refused")
    msg = draft_step(db, case, pb, pb.steps[0], use_llm=False)
    with pytest.raises(NotApproved):
        send_message(db, msg.id)


def test_demo_upload_cap_is_5mb(demo: None) -> None:
    assert get_settings().upload_limit_mb == 5


def test_demo_cases_auto_delete_after_24h(agent_env: AgentEnv, demo: None) -> None:  # noqa: F811
    with freeze_time(DAY0) as clock:
        old = agent_env.new_case(description=LED_TEXT, country="PK")
        clock.tick(timedelta(hours=20))
        new = agent_env.new_case(description=LED_TEXT, country="PK")
        clock.tick(timedelta(hours=5))
        assert jobs.cleanup_demo_cases() == [old]
    with agent_env.session() as s:
        assert [c.id for c in s.scalars(select(Case))] == [new]


def test_no_cleanup_outside_demo_mode(agent_env: AgentEnv) -> None:  # noqa: F811
    with freeze_time(DAY0) as clock:
        agent_env.new_case(description=LED_TEXT, country="PK")
        clock.tick(timedelta(days=3))
        assert jobs.cleanup_demo_cases() == []


def test_led_facts_fixture_has_no_secrets() -> None:
    assert all(mask_pii(v) == v for v in LED_FACTS.values())
