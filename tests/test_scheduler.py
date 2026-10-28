from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from freezegun import freeze_time
from sqlalchemy.orm import Session

from escalate.agent.deadlines import deadline_status, is_late
from escalate.agent.judge_reply import judge, record_reply
from escalate.agent.pick_next import pick_next
from escalate.db.models import CaseFact, CaseStatus, Message
from escalate.playbooks.loader import get_playbook
from escalate.scheduler import jobs
from tests.factories import LED_FACTS, led_case
from tests.fakes.fake_llm import FakeLLM
from tests.fakes.manual_scheduler import ManualScheduler

DAY0 = datetime(2026, 10, 1, 10, 0)


@pytest.fixture
def wakes() -> Iterator[list[tuple[int, str]]]:
    calls: list[tuple[int, str]] = []
    jobs.set_wake_handler(lambda c, s: calls.append((c, s)))
    yield calls
    jobs.set_wake_handler(None)


@pytest.fixture
def job_db(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'jobs.db'}"


def _sched(url: str) -> ManualScheduler:
    s = ManualScheduler(url)
    s.start()
    return s


def test_seven_day_wait_fires_once_on_day_seven(job_db: str, wakes: list) -> None:
    with freeze_time(DAY0) as clock:
        sched = _sched(job_db)
        jid = jobs.schedule_wake(sched, 1, "s1_written_demand", DAY0 + timedelta(days=7))
        assert jid == "case-1-step-s1_written_demand"
        for _ in range(6):
            clock.tick(timedelta(days=1))
            sched.tick()
        assert wakes == []
        clock.tick(timedelta(days=1))  # day 7
        sched.tick()
        assert wakes == [(1, "s1_written_demand")]
        clock.tick(timedelta(days=3))
        sched.tick()
        assert wakes == [(1, "s1_written_demand")]  # fired once only
        sched.shutdown()


def test_wake_survives_restart(job_db: str, wakes: list) -> None:
    with freeze_time(DAY0) as clock:
        first = _sched(job_db)
        jobs.schedule_wake(first, 7, "s3_legal_notice", DAY0 + timedelta(days=15))
        first.shutdown()

        clock.tick(timedelta(days=15))
        second = _sched(job_db)  # a brand-new scheduler on the same job store
        assert [j.id for j in second.get_jobs()] == ["case-7-step-s3_legal_notice"]
        second.tick()
        assert wakes == [(7, "s3_legal_notice")]
        second.shutdown()


def test_missed_wake_fires_after_long_downtime(job_db: str, wakes: list) -> None:
    with freeze_time(DAY0) as clock:
        first = _sched(job_db)
        jobs.schedule_wake(first, 2, "s1", DAY0 + timedelta(days=5))
        first.shutdown()
        clock.tick(timedelta(days=40))  # machine was off for weeks
        second = _sched(job_db)
        second.tick()
        assert wakes == [(2, "s1")]
        second.shutdown()


def test_reschedule_replaces_not_duplicates(job_db: str, wakes: list) -> None:
    with freeze_time(DAY0) as clock:
        sched = _sched(job_db)
        jobs.schedule_wake(sched, 3, "s1", DAY0 + timedelta(days=5))
        jobs.schedule_wake(sched, 3, "s1", DAY0 + timedelta(days=7))
        assert len(sched.get_jobs()) == 1
        clock.tick(timedelta(days=5))
        sched.tick()
        assert wakes == []
        clock.tick(timedelta(days=2))
        sched.tick()
        assert wakes == [(3, "s1")]
        sched.shutdown()


def test_cancel_case_jobs(job_db: str) -> None:
    with freeze_time(DAY0):
        sched = _sched(job_db)
        jobs.schedule_wake(sched, 4, "s1", DAY0 + timedelta(days=5))
        jobs.schedule_wake(sched, 44, "s1", DAY0 + timedelta(days=5))
        assert jobs.cancel_case_jobs(sched, 4) == 1
        assert [j.id for j in sched.get_jobs()] == ["case-44-step-s1"]
        sched.shutdown()


# --- deadlines -------------------------------------------------------------------


def _sent_notice(db: Session, sent: datetime) -> None:
    case = led_case(db, playbook_id="pk-ecommerce-refund-refused")
    db.add(
        Message(
            case_id=case.id,
            step_id="s3_legal_notice",
            direction="out",
            channel="post",
            body="notice",
            status="sent",
            sent_at=sent,
        )
    )
    case.status = CaseStatus.WAITING_REPLY
    db.flush()
    db.refresh(case)
    return case


def test_court_limit_warns_at_ten_days_left(db: Session) -> None:
    pb = get_playbook("pk-ecommerce-refund-refused")
    case = _sent_notice(db, DAY0)  # notice period ends day 15, filing limit day 45
    with freeze_time(DAY0 + timedelta(days=34)):  # 11 days left
        assert jobs.scan_case_deadlines(db, case) == []
    with freeze_time(DAY0 + timedelta(days=35)):  # 10 days left
        [ev] = jobs.scan_case_deadlines(db, case)
        assert ev.payload["days_left"] == 10
        assert ev.payload["message"] == "deadline in 10 days"
        assert jobs.scan_case_deadlines(db, case) == []  # once per day
    with freeze_time(DAY0 + timedelta(days=46)):
        assert is_late(case, pb)
        [ev] = jobs.scan_case_deadlines(db, case)
        assert ev.payload["late"] is True


def test_cause_of_action_fact_overrides_step(db: Session) -> None:
    pb = get_playbook("pk-ecommerce-refund-refused")
    case = _sent_notice(db, DAY0)
    db.add(CaseFact(case_id=case.id, key="cause_of_action_on", value="2026-10-10"))
    db.flush()
    db.refresh(case)
    [st] = deadline_status(case, pb, today=DAY0.date())
    assert st.due.isoformat() == "2026-11-09"


def test_daily_scan_job_uses_global_session(db: Session) -> None:
    case = _sent_notice(db, DAY0)
    db.commit()
    with freeze_time(DAY0 + timedelta(days=36)):
        assert jobs.scan_deadlines() == 1
    db.expire_all()
    assert case.events[-1].type == "deadline_warning"


# --- judge reply -----------------------------------------------------------------


def test_led_promise_when_claim_approved_is_refused() -> None:
    # Even if a small model calls it "partial", an undated promise is refused in code.
    llm = FakeLLM(
        script=[
            {
                "verdict": "partial",
                "promise": "replace the LED when the company claim is approved",
                "promise_date": None,
                "reason": "they promised a replacement",
            }
        ]
    )
    j = judge(
        "Dear customer, we will replace the LED when the company claim is approved.",
        LED_FACTS["remedy_wanted"],
        llm=llm,
    )
    assert j.verdict == "refused"
    assert "undated promise" in j.reason
    prompt = llm.calls[0][0]
    assert "when the company claim is approved" in prompt
    assert llm.calls[0][1] == "fast"


def test_dated_promise_keeps_model_verdict() -> None:
    llm = FakeLLM(
        script=[
            {
                "verdict": "resolved",
                "promise": "refund",
                "promise_date": "2026-11-02",
                "reason": "refund on date",
            }
        ]
    )
    j = judge("We will refund you on 2 November 2026.", "refund", llm=llm)
    assert j.verdict == "resolved"


def test_timer_is_no_reply_without_model() -> None:
    llm = FakeLLM()
    assert judge(None, "refund", llm=llm).verdict == "no_reply"
    assert llm.calls == []


def test_record_reply(db: Session) -> None:
    case = led_case(db, current_step="s1_written_demand")
    msg = record_reply(db, case, "  We refuse.  ")
    assert (msg.direction, msg.status, msg.body, msg.step_id) == (
        "in",
        "received",
        "We refuse.",
        "s1_written_demand",
    )
    assert case.events[-1].type == "reply_logged"


# --- pick next -------------------------------------------------------------------


def test_pick_next_follows_ladder() -> None:
    pb = get_playbook("pk-ecommerce-refund-refused")
    facts = dict(LED_FACTS)
    assert pick_next(pb, "s1_seller_written", "refused", facts) == "s3_legal_notice"
    # no platform: s2_platform's `when` fails, so no reply skips to the legal notice
    assert pick_next(pb, "s1_seller_written", "no_reply", facts) == "s3_legal_notice"
    facts["platform_name"] = "Daraz"
    assert pick_next(pb, "s1_seller_written", "no_reply", facts) == "s2_platform"
    assert pick_next(pb, "s3_legal_notice", "no_reply", facts) == "s4_consumer_court"
    assert pick_next(pb, "s4_consumer_court", "no_reply", facts) is None
    assert pick_next(pb, "s1_seller_written", "resolved", facts) is None


def test_pick_next_partial_uses_on_partial() -> None:
    pb = get_playbook("intl-generic-refund-refused")
    assert pick_next(pb, "s1_written_demand", "partial", LED_FACTS) == "s2_final_notice"
