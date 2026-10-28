"""End to end with the fake LLM, fake SMTP and freezegun: the broken-LED case up the PK ladder."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from freezegun import freeze_time
from langgraph.types import Command

from escalate.agent import runner
from escalate.agent.approval import UnsupportedFacts
from escalate.channels import NotApproved, ProofRequired
from escalate.db import session as db_session
from escalate.db.models import CaseStatus, Message
from escalate.evidence.store import save_upload
from tests.agent_env import AgentEnv, agent_env, make_llm  # noqa: F401
from tests.factories import LED_FACTS, LED_TEXT
from tests.fakes.fake_smtp import FakeSMTP

DAY0 = datetime(2026, 10, 1, 9, 0)
FIX = Path(__file__).parent / "fixtures"


def _facts_with_platform() -> dict[str, str]:
    return {**LED_FACTS, "platform_name": "Daraz"}


def _new_led(env: AgentEnv) -> int:
    return env.new_case(description=LED_TEXT, country="PK", region="PK-SD")


def _tick(env: AgentEnv, clock: object, days: int) -> None:
    clock.tick(timedelta(days=days))  # type: ignore[attr-defined]
    env.scheduler.tick()


def test_led_case_runs_up_the_ladder(agent_env: AgentEnv) -> None:  # noqa: F811
    env = agent_env
    env.llm.rules[0] = ("You extract facts", make_llm(_facts_with_platform()).rules[0][1])
    with freeze_time(DAY0) as clock:
        cid = _new_led(env)

        # intake -> classify -> draft s1 -> approval
        r = runner.start_case(cid)
        assert r.waiting_for == "approve_draft"
        draft = r.pending["draft"]  # type: ignore[index]
        assert draft["recipient"] == "support@brightmart.example"
        assert "BM-48213" in draft["body"] and "not legal advice" in draft["body"]
        case = env.case(cid)
        assert case.playbook_id == "pk-ecommerce-refund-refused"
        assert case.status == CaseStatus.AWAITING_APPROVAL

        # approve -> email sent -> waiting 5 days
        r = runner.resume_with_decision(cid, "approve")
        assert r.waiting_for == "waiting_reply"
        assert len(FakeSMTP.all_sent()) == 1
        assert FakeSMTP.all_sent()[0]["To"] == "support@brightmart.example"
        assert [j.id for j in env.scheduler.get_jobs()] == [f"case-{cid}-step-s1_seller_written"]

        # 4 days: nothing; day 5: timeout -> no_reply -> platform escalation draft
        _tick(env, clock, 4)
        assert runner.pending(cid)["type"] == "waiting_reply"  # type: ignore[index]
        _tick(env, clock, 1)
        p = runner.pending(cid)
        assert p["type"] == "approve_draft"  # type: ignore[index]
        assert env.case(cid).current_step == "s2_platform"

        # approve the follow-up; it's a web form, so the user confirms they submitted it
        r = runner.resume_with_decision(cid, "approve")
        assert r.waiting_for == "confirm_delivery"
        r = runner.confirm_delivery(cid)
        assert r.waiting_for == "waiting_reply"
        assert len(FakeSMTP.all_sent()) == 1  # web form: nothing emailed

        # 15 days pass -> legal notice; it needs the seller's postal address first
        _tick(env, clock, 15)
        p = runner.pending(cid)
        assert p == {"type": "questions", "missing": ["seller_address"]}
        r = runner.resume_with_answers(cid, {"seller_address": "Shop 4, Saddar, Karachi"})
        assert r.waiting_for == "approve_draft"
        assert env.case(cid).current_step == "s3_legal_notice"

        # approve the notice -> printable post; proof of delivery required
        r = runner.resume_with_decision(cid, "approve")
        assert r.waiting_for == "confirm_delivery"
        with pytest.raises(ProofRequired):
            runner.confirm_delivery(cid)
        with db_session.session_scope() as s:
            proof = save_upload(
                s, cid, "registry_receipt.txt", b"TCS receipt 2026-10-21", env.settings
            )
            proof_id = proof.id
        r = runner.confirm_delivery(cid, proof_id)
        assert r.waiting_for == "waiting_reply"

        # 15 days -> consumer court complaint, after asking for the buyer's address
        _tick(env, clock, 15)
        assert runner.pending(cid) == {"type": "questions", "missing": ["buyer_address"]}
        r = runner.resume_with_answers(cid, {"buyer_address": "House 9, Block 2, Karachi"})
        assert r.waiting_for == "approve_draft"
        assert env.case(cid).current_step == "s4_consumer_court"

    events = env.event_types(cid)
    expected_order = [
        "case_started",
        "classified",
        "playbook_selected",
        "facts_extracted",
        "draft_created",
        "fact_checked",
        "message_approved",
        "message_sent",
        "waiting_reply",
        "wait_expired",
        "reply_judged",
        "next_step",
        "draft_created",
        "message_approved",
        "awaiting_user_delivery",
        "message_sent",
        "wait_expired",
        "next_step",
        "answers_saved",
        "draft_created",
        "message_approved",
        "evidence_added",
        "message_sent",
        "wait_expired",
        "next_step",
        "answers_saved",
        "draft_created",
    ]
    it = iter(events)
    missing = [e for e in expected_order if e not in it]  # subsequence check, in order
    assert missing == [], events


def test_led_promise_reply_jumps_to_legal_notice(agent_env: AgentEnv) -> None:  # noqa: F811
    env = agent_env
    env.llm.rules[4] = (
        "A company replied",
        {
            "verdict": "partial",
            "promise": "replace when the company claim is approved",
            "promise_date": None,
            "reason": "promise",
        },
    )
    with freeze_time(DAY0) as clock:
        cid = _new_led(env)
        runner.start_case(cid)
        runner.resume_with_decision(cid, "approve")
        clock.tick(timedelta(days=2))
        r = runner.resume_with_reply(
            cid, "We will replace the LED when the company claim is approved."
        )
        assert r.waiting_for == "questions"  # legal notice needs seller_address
        assert env.case(cid).current_step == "s3_legal_notice"
        assert env.scheduler.get_jobs() == []  # the 5-day wake was cancelled
        _tick(env, clock, 5)  # nothing fires
        assert runner.pending(cid)["type"] == "questions"  # type: ignore[index]
    events = env.event_types(cid)
    assert "reply_logged" in events
    with env.session() as s:
        replies = s.query(Message).filter_by(case_id=cid, direction="in").all()
        assert replies[0].body.startswith("We will replace")


def test_resolved_reply_ends_case(agent_env: AgentEnv) -> None:  # noqa: F811
    env = agent_env
    env.llm.rules[4] = (
        "A company replied",
        {"verdict": "resolved", "promise": None, "promise_date": None, "reason": "refunded"},
    )
    with freeze_time(DAY0):
        cid = _new_led(env)
        runner.start_case(cid)
        runner.resume_with_decision(cid, "approve")
        r = runner.resume_with_reply(cid, "We have refunded PKR 45,000 today.")
    assert r.pending is None
    assert env.case(cid).status == CaseStatus.RESOLVED


def test_reject_redrafts_with_reason(agent_env: AgentEnv) -> None:  # noqa: F811
    env = agent_env
    with freeze_time(DAY0):
        cid = _new_led(env)
        first = runner.start_case(cid).pending["draft"]["message_id"]  # type: ignore[index]
        r = runner.resume_with_decision(cid, "reject", reason="mention the tracking number")
        assert r.waiting_for == "approve_draft"
        assert r.pending["draft"]["message_id"] != first  # type: ignore[index]
    assert env.llm.prompts_containing("mention the tracking number")
    assert FakeSMTP.all_sent() == []


def test_edit_with_invented_amount_is_blocked(agent_env: AgentEnv) -> None:  # noqa: F811
    env = agent_env
    with freeze_time(DAY0):
        cid = _new_led(env)
        body = runner.start_case(cid).pending["draft"]["body"]  # type: ignore[index]
        with pytest.raises(UnsupportedFacts):
            runner.resume_with_decision(cid, "approve", edited_body=body + "\nPay 99,999 too.")
        assert runner.pending(cid)["type"] == "approve_draft"  # type: ignore[index]
    assert FakeSMTP.all_sent() == []


def test_resuming_graph_with_approve_does_not_bypass_gate(agent_env: AgentEnv) -> None:  # noqa: F811
    env = agent_env
    with freeze_time(DAY0):
        cid = _new_led(env)
        runner.start_case(cid)
        cfg = {"configurable": {"thread_id": str(cid)}}
        with pytest.raises(NotApproved):
            runner.graph().invoke(Command(resume={"decision": "approve"}), cfg)  # type: ignore[arg-type]
    assert FakeSMTP.all_sent() == []


def test_missing_facts_are_asked_before_drafting(agent_env: AgentEnv) -> None:  # noqa: F811
    env = agent_env
    partial = {k: v for k, v in LED_FACTS.items() if k not in ("order_id", "seller_contact")}
    env.llm.rules[0] = ("You extract facts", make_llm(partial).rules[0][1])
    with freeze_time(DAY0):
        cid = _new_led(env)
        r = runner.start_case(cid)
        assert r.pending == {"type": "questions", "missing": ["seller_contact", "order_id"]}
        assert not env.llm.prompts_containing("You write the")
        r = runner.resume_with_answers(
            cid, {"seller_contact": "support@brightmart.example", "order_id": "BM-48213"}
        )
        assert r.waiting_for == "approve_draft"
    assert len(env.llm.prompts_containing("You extract facts")) == 1  # not re-extracted


def test_stale_timeout_is_ignored(agent_env: AgentEnv) -> None:  # noqa: F811
    env = agent_env
    with freeze_time(DAY0):
        cid = _new_led(env)
        runner.start_case(cid)
        assert runner.resume_timeout(cid, "s1_seller_written") is None  # not waiting yet


def test_withdraw_cancels_wake(agent_env: AgentEnv) -> None:  # noqa: F811
    env = agent_env
    with freeze_time(DAY0) as clock:
        cid = _new_led(env)
        runner.start_case(cid)
        runner.resume_with_decision(cid, "approve")
        runner.withdraw(cid, "settled privately")
        assert env.scheduler.get_jobs() == []
        _tick(env, clock, 10)
    assert env.case(cid).status == CaseStatus.WITHDRAWN


def test_wrong_input_for_state_is_refused(agent_env: AgentEnv) -> None:  # noqa: F811
    env = agent_env
    with freeze_time(DAY0):
        cid = _new_led(env)
        runner.start_case(cid)
        with pytest.raises(runner.RunnerError):
            runner.resume_with_reply(cid, "hello")


def test_smtp_failure_can_be_retried(agent_env: AgentEnv) -> None:  # noqa: F811
    env = agent_env

    class Down(FakeSMTP):
        def login(self, user: str, password: str) -> None:
            raise OSError("network down")

    from escalate.channels import override_channel
    from escalate.channels.email_smtp import SmtpChannel

    good = SmtpChannel(
        env.settings.model_copy(update={"smtp_user": "a@b.co", "smtp_app_password": "x"}),
        smtp_factory=FakeSMTP,
    )
    override_channel("email", SmtpChannel(good.settings, smtp_factory=Down))
    with freeze_time(DAY0):
        cid = _new_led(env)
        runner.start_case(cid)
        with pytest.raises(OSError):
            runner.resume_with_decision(cid, "approve")
        override_channel("email", good)
        r = runner.retry(cid)
        assert r.waiting_for == "waiting_reply"
    assert len(FakeSMTP.all_sent()) == 1
