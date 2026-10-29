from datetime import date, datetime

import pytest
from freezegun import freeze_time

from escalate.agent import runner
from escalate.agent.fact_check import code_check
from escalate.db import session as db_session
from escalate.evidence.store import save_upload
from escalate.playbooks.loader import get_playbook
from escalate.templates_engine import disclaimer, render_step
from tests.agent_env import AgentEnv, agent_env, approve_pending, make_llm  # noqa: F401
from tests.factories import LED_FACTS, LED_TEXT

PB = "pk-ecommerce-refund-refused"
FULL = {
    **LED_FACTS,
    "platform_name": "Daraz",
    "buyer_address": "House 9, Block 2, Karachi",
    "seller_address": "Shop 4, Saddar, Karachi",
}
TODAY = date(2026, 10, 28)


@pytest.mark.parametrize("language", ["en", "ur"])
@pytest.mark.parametrize(
    "step_id", ["s1_seller_written", "s2_platform", "s3_legal_notice", "s4_consumer_court"]
)
def test_every_pk_template_renders_with_led_facts(step_id: str, language: str) -> None:
    pb = get_playbook(PB)
    r = render_step(pb, pb.step(step_id), FULL, language, today=TODAY, country="PK")
    text = f"{r.subject}\n{r.body}"
    assert r.subject
    assert "BM-48213" in text
    assert "PKR 45,000.00" in text
    assert "None" not in text and "{{" not in text
    # nothing but facts and the template's own fixed text
    reference = render_step(pb, pb.step(step_id), FULL, language, today=TODAY, country="PK")
    assert code_check(text, FULL, f"{reference.subject}\n{reference.body}") == []


def test_urdu_template_is_urdu() -> None:
    pb = get_playbook(PB)
    r = render_step(pb, pb.step("s3_legal_notice"), FULL, "ur", today=TODAY, country="PK")
    assert "قانونی نوٹس" in r.body
    assert "پندرہ (15) دن" in r.body


def test_legal_notice_reads_correctly() -> None:
    pb = get_playbook(PB)
    r = render_step(pb, pb.step("s3_legal_notice"), FULL, "en", today=TODAY, country="PK")
    assert r.subject == "Legal notice: order BM-48213"
    assert "To: BrightMart Electronics, Shop 4, Saddar, Karachi" in r.body
    assert "Date: 28 October 2026" in r.body
    assert "within fifteen (15) days" in r.body
    assert "District Consumer Court" in r.body
    assert '"we will replace it when the company claim is approved"' in r.body


def test_late_court_complaint_includes_condonation() -> None:
    pb = get_playbook(PB)
    step = pb.step("s4_consumer_court")
    on_time = render_step(pb, step, FULL, "en", today=TODAY, country="PK")
    late = render_step(pb, step, FULL, "en", today=TODAY, late=True, country="PK")
    assert "CONDONATION" not in on_time.body
    assert "APPLICATION FOR CONDONATION OF DELAY" in late.body
    assert late.body.index("PRAYER") < late.body.index("CONDONATION")


def test_urdu_disclaimer() -> None:
    assert "قانونی مشورہ نہیں" in disclaimer("ur", False)
    assert "not legal advice" in disclaimer("ur", False)


def test_urdu_digits_are_fact_checked() -> None:
    assert code_check("رقم ۹۹۰۰۰ روپے", LED_FACTS) == ["number 99000 is not in the case facts"]
    assert code_check("رقم ۴۵۰۰۰ روپے", LED_FACTS) == []


def test_late_case_gets_condonation_through_the_graph(agent_env: AgentEnv) -> None:  # noqa: F811
    env = agent_env
    facts = {**FULL, "cause_of_action_on": "2026-03-01"}  # filing limit long gone
    env.llm.rules[0] = ("You extract facts", make_llm(facts).rules[0][1])
    with freeze_time(datetime(2026, 10, 1, 9)):
        cid = env.new_case(description=LED_TEXT, country="PK", region="PK-SD")
        runner.start_case(cid)
        approve_pending(cid)
        r = runner.resume_with_reply(cid, "We refuse. Read our policy.")
        assert env.case(cid).current_step == "s3_legal_notice"  # on_refused skips the platform
        assert "CONDONATION" not in r.pending["draft"]["body"]  # type: ignore[index]
        approve_pending(cid)
        with db_session.session_scope() as s:
            proof_id = save_upload(s, cid, "tcs.txt", b"TCS receipt", env.settings).id
        runner.confirm_delivery(cid, proof_id)
        r = runner.resume_with_reply(cid, "No.")
        assert env.case(cid).current_step == "s4_consumer_court"
        body = r.pending["draft"]["body"]  # type: ignore[index]
        assert "APPLICATION FOR CONDONATION OF DELAY" in body
        assert "BEFORE THE DISTRICT CONSUMER COURT" in body
    assert "next_step" in env.event_types(cid)
