"""Subscription-cancel and scam flows, end to end with the fake LLM."""

import shutil
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml
from freezegun import freeze_time

from escalate.agent import runner
from escalate.agent.checklist import load_checklist
from escalate.db.models import CaseStatus
from escalate.playbooks.validate import validate
from tests.agent_env import AgentEnv, agent_env, make_llm  # noqa: F401
from tests.fakes.fake_smtp import FakeSMTP

DAY0 = datetime(2026, 10, 1, 9, 0)
REPO = Path(__file__).resolve().parents[1]

GYM_TEXT = (
    "I'm Tom Hughes. I cancelled my FitLife membership FL-90211 by email on 2026-05-01 but they "
    "charged me twice since. I want the cancellation confirmed and the payments refunded."
)
GYM_FACTS = {
    "buyer_name": "Tom Hughes",
    "company_name": "FitLife",
    "company_contact": "members@fitlife.example",
    "account_id": "FL-90211",
    "cancel_requested_on": "2026-05-01",
    "remedy_wanted": "confirm the cancellation and refund both charges",
    "amount": "29.99",
    "currency": "GBP",
    "charges_after_cancel": "GBP 29.99 on 2026-06-01; GBP 29.99 on 2026-07-01",
}
SCAM_TEXT = (
    "I am Usman Tariq. Yesterday someone on Facebook sold me a bike, I sent Rs 60,000 by bank "
    "transfer from Meezan Bank, ref MZ-882100. Now the seller's number is off."
)
SCAM_FACTS = {
    "buyer_name": "Usman Tariq",
    "amount": "60000",
    "currency": "PKR",
    "paid_on": "2026-09-30",
    "payment_method": "bank transfer",
    "scam_description": "A seller on Facebook took payment for a bike and then disappeared.",
    "bank_name": "Meezan Bank",
    "bank_contact": "fraud@meezan.example",
    "transaction_id": "MZ-882100",
}


def test_subscription_cancel_flow(agent_env: AgentEnv) -> None:  # noqa: F811
    env = agent_env
    env.llm.rules[0] = ("You extract facts", make_llm(GYM_FACTS).rules[0][1])
    env.llm.rules[1] = (
        "Classify this complaint",
        make_llm(
            classification={"case_type": "subscription_cancel", "country": "GB", "region": None}
        ).rules[1][1],
    )
    with freeze_time(DAY0) as clock:
        cid = env.new_case(description=GYM_TEXT, country="GB")
        r = runner.start_case(cid)
        assert env.case(cid).playbook_id == "intl-generic-subscription-cancel"
        draft = r.pending["draft"]  # type: ignore[index]
        assert draft["subject"] == "Cancel my subscription (account FL-90211)"
        assert "Check the rules in your country" in draft["body"]
        runner.resume_with_decision(cid, "approve")
        assert FakeSMTP.all_sent()[0]["To"] == "members@fitlife.example"

        clock.tick(timedelta(days=7))
        env.scheduler.tick()
        draft = runner.pending(cid)["draft"]  # type: ignore[index]
        assert "Final notice" in draft["subject"]
        assert "GBP 29.99 on 2026-06-01" in draft["body"]  # the charges are listed
        runner.resume_with_decision(cid, "approve")

        # no reply in 14 days -> card dispute, which needs the card issuer first
        clock.tick(timedelta(days=14))
        env.scheduler.tick()
        assert runner.pending(cid) == {"type": "questions", "missing": ["card_issuer"]}
        r = runner.resume_with_answers(
            cid, {"card_issuer": "Example Bank", "card_issuer_contact": "disputes@bank.example"}
        )
        draft = r.pending["draft"]  # type: ignore[index]
        assert draft["recipient"] == "disputes@bank.example"
        assert "I dispute charges taken by FitLife" in draft["body"]
        runner.resume_with_decision(cid, "approve")

        clock.tick(timedelta(days=30))
        env.scheduler.tick()
        assert runner.pending(cid) == {"type": "questions", "missing": ["authority_name"]}
    assert len(FakeSMTP.all_sent()) == 3


def test_scam_shows_checklist_before_anything(agent_env: AgentEnv) -> None:  # noqa: F811
    env = agent_env
    env.llm.rules[0] = ("You extract facts", make_llm(SCAM_FACTS).rules[0][1])
    env.llm.rules[1] = (
        "Classify this complaint",
        make_llm(classification={"case_type": "scam", "urgent": True}).rules[1][1],
    )
    with freeze_time(DAY0) as clock:
        cid = env.new_case(description=SCAM_TEXT, country="PK")
        r = runner.start_case(cid)

        # 1. checklist first: no extraction, no questions, no letter yet
        assert r.waiting_for == "urgent_checklist"
        titles = [i["title"] for i in r.pending["items"]]  # type: ignore[index]
        assert titles[0].startswith("Call your bank")
        assert env.case(cid).status == CaseStatus.URGENT
        assert not env.llm.prompts_containing("You extract facts")
        assert not env.llm.prompts_containing("You write the")
        assert "draft_created" not in env.event_types(cid)

        # 2. after acknowledging: bank fraud report draft
        r = runner.acknowledge_checklist(cid)
        assert r.waiting_for == "approve_draft"
        draft = r.pending["draft"]  # type: ignore[index]
        assert draft["recipient"] == "fraud@meezan.example"
        assert "MZ-882100" in draft["body"] and "PKR 60,000.00" in draft["body"]
        runner.resume_with_decision(cid, "approve")

        # 3. bank doesn't help in 10 days -> police report (by post, user delivers it)
        clock.tick(timedelta(days=10))
        env.scheduler.tick()
        draft = runner.pending(cid)["draft"]  # type: ignore[index]
        assert draft["channel"] == "post"
        assert "I wish to report a fraud." in draft["body"]
        assert "I have reported the payment to Meezan Bank." in draft["body"]

    events = env.event_types(cid)
    assert events.index("urgent_checklist_acknowledged") < events.index("draft_created")
    # the prompts never ask the user for secrets
    asked = " ".join(p for p, _ in env.llm.calls).lower()
    assert "password" not in asked and "otp" not in asked


def test_checklist_generic_fallback_and_warnings() -> None:
    cl = load_checklist("ZZ")
    assert cl.country == "INTL"
    assert any("recovery" in w.lower() for w in cl.warnings)
    assert any("OTP" in w for w in cl.warnings)
    assert cl.items[0].urgent


def test_country_checklist_overrides_generic(tmp_path: Path) -> None:
    (tmp_path / "xx").mkdir()
    (tmp_path / "xx" / "scam_checklist.yaml").write_text(
        yaml.safe_dump({"country": "XX", "items": [{"id": "a", "title": "Call XX bank"}]})
    )
    assert load_checklist("XX", tmp_path).items[0].title == "Call XX bank"
    assert load_checklist(None, REPO / "playbooks").country == "INTL"


def test_validator_rejects_secret_facts(tmp_path: Path) -> None:
    shutil.copytree(REPO / "playbooks", tmp_path / "playbooks")
    shutil.copytree(REPO / "templates", tmp_path / "templates")
    path = tmp_path / "playbooks/intl/generic/scam.yaml"
    data = yaml.safe_load(path.read_text())
    data["optional_facts"].append("card_pin")
    path.write_text(yaml.safe_dump(data))
    errors = validate(tmp_path / "playbooks", tmp_path / "templates").errors
    assert any("card_pin" in e and "secret" in e for e in errors)


@pytest.mark.parametrize("key", ["card_last4", "pinned_note", "shipping"])
def test_validator_allows_innocent_names(key: str) -> None:
    from escalate.playbooks.validate import FORBIDDEN_FACT

    assert not FORBIDDEN_FACT.search(key)
