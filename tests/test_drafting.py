from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from escalate.agent.classify import apply_playbook, classify
from escalate.agent.draft import draft_step
from escalate.db.models import Case, CaseFact, CaseStatus
from escalate.playbooks.loader import get_playbook
from escalate.templates_engine import (
    MissingFacts,
    MissingPlaceholder,
    render_file,
    render_step,
    split_subject,
)
from tests.factories import LED_FACTS, led_case
from tests.fakes.fake_llm import FakeLLM


def _classifier(**kw: object) -> FakeLLM:
    reply = {
        "case_type": "refund_refused",
        "country": None,
        "region": None,
        "language": "en",
        "urgent": False,
        "reason": "refund",
    }
    reply.update(kw)
    return FakeLLM(script=[reply])


# --- classification ------------------------------------------------------------


def test_classify_unknown_country_falls_back_to_generic(db: Session) -> None:
    case = Case(description="Shop in Brazil won't refund my blender")
    db.add(case)
    db.flush()
    llm = _classifier(country="BR", region="BR-SP", language="pt")
    result = classify(db, case, llm=llm)
    assert result.language == "pt"
    assert case.country == "BR" and case.region == "BR-SP"
    assert case.playbook_id == "intl-generic-refund-refused"
    assert case.playbook_version == "0.1.0"
    assert llm.calls[0][1] == "fast"
    assert [e.type for e in case.events] == ["classified", "playbook_selected"]


def test_classify_users_country_wins_and_pk_pack_is_used(db: Session) -> None:
    case = led_case(db, case_type=None, region=None)
    classify(db, case, llm=_classifier(country="IN", region="IN-MH"))
    assert case.country == "PK"
    assert case.region is None  # IN-MH does not belong to PK
    assert case.playbook_id == "pk-ecommerce-refund-refused"
    assert case.currency == "PKR"
    assert case.amount == Decimal("45000")


def test_classify_rejects_bad_iso_codes_and_other_type(db: Session) -> None:
    case = Case(description="something odd")
    db.add(case)
    db.flush()
    classify(db, case, llm=_classifier(case_type="other", country="Pakistan", region="sindh"))
    assert case.country is None and case.region is None
    assert case.case_type == "refund_refused"
    assert case.playbook_id == "intl-generic-refund-refused"


def test_apply_playbook_picks_scam_generic(db: Session) -> None:
    case = Case(description="x", country="PK", case_type="scam")
    db.add(case)
    db.flush()
    assert apply_playbook(db, case).id == "intl-generic-scam"


# --- templates -------------------------------------------------------------------


def test_split_subject() -> None:
    r = split_subject("Subject: Hello\n\nBody line\n")
    assert (r.subject, r.body) == ("Hello", "Body line\n")


def test_missing_required_fact_blocks_drafting(db: Session) -> None:
    case = led_case(db)
    db.delete(next(f for f in case.facts if f.key == "order_id"))
    db.flush()
    db.refresh(case)
    pb = get_playbook("intl-generic-refund-refused")
    llm = FakeLLM()
    with pytest.raises(MissingFacts) as err:
        draft_step(db, case, pb, pb.steps[0], llm=llm)
    assert err.value.keys == ["order_id"]
    assert llm.calls == []
    assert case.messages == []


def test_step_requires_blocks_drafting() -> None:
    pb = get_playbook("intl-generic-refund-refused")
    with pytest.raises(MissingFacts) as err:
        render_step(pb, pb.step("s3_authority"), LED_FACTS, "en")
    assert err.value.keys == ["authority_name"]


def test_strict_undefined_placeholder_raises(tmp_path: object) -> None:
    from pathlib import Path

    p = Path(str(tmp_path)) / "t.md.j2"
    p.write_text("Hello {{ not_a_fact }}")
    with pytest.raises(MissingPlaceholder):
        render_file(p, {})


def test_generic_template_renders_facts_only() -> None:
    pb = get_playbook("intl-generic-refund-refused")
    r = render_step(pb, pb.steps[0], LED_FACTS, "en", today=date(2026, 10, 28), country="PK")
    assert r.subject == "Refund request for order BM-48213"
    assert "PKR 45,000.00" in r.body
    assert "4 November 2026" in r.body  # reply_by = today + 7 days, en_PK date style
    assert "tracking number 7731990" in r.body
    assert "None" not in r.body


# --- drafting --------------------------------------------------------------------


def test_draft_polishes_and_appends_disclaimer(db: Session) -> None:
    case = led_case(db, country="BR", region=None)
    pb = get_playbook("intl-generic-refund-refused")
    llm = FakeLLM(script=[{"subject": "Refund for BM-48213", "body": "Dear BrightMart..."}])
    msg = draft_step(db, case, pb, pb.steps[0], llm=llm)

    assert msg.status == "draft"
    assert msg.subject == "Refund for BM-48213"
    assert msg.recipient == "support@brightmart.example"
    assert msg.channel == "email"
    assert "not legal advice" in msg.body
    assert "Check the rules in your country" in msg.body  # generic playbook
    assert case.status == CaseStatus.AWAITING_APPROVAL
    assert case.current_step == "s1_written_demand"
    prompt = llm.calls[0][0]
    assert "Refund request for order BM-48213" in prompt  # the rendered template is given
    assert '"order_id": "BM-48213"' in prompt
    assert "Language: en" in prompt


def test_draft_falls_back_to_template_when_model_fails(db: Session) -> None:
    case = led_case(db)
    pb = get_playbook("intl-generic-refund-refused")
    msg = draft_step(db, case, pb, pb.steps[0], llm=FakeLLM(script=["x", "y", "z"]))
    assert "BM-48213" in msg.body
    assert "not legal advice" in msg.body


def test_redraft_supersedes_old_draft(db: Session) -> None:
    case = led_case(db)
    pb = get_playbook("intl-generic-refund-refused")
    first = draft_step(db, case, pb, pb.steps[0], use_llm=False)
    second = draft_step(db, case, pb, pb.steps[0], use_llm=False)
    assert first.status == "superseded"
    assert second.status == "draft"


def test_feedback_is_passed_to_model(db: Session) -> None:
    case = led_case(db)
    pb = get_playbook("intl-generic-refund-refused")
    llm = FakeLLM(script=[{"subject": "s", "body": "b"}])
    draft_step(db, case, pb, pb.steps[0], llm=llm, feedback=["amount 50000 is not a fact"])
    assert "amount 50000 is not a fact" in llm.calls[0][0]


def test_case_fact_factory_has_led_facts(db: Session) -> None:
    case = led_case(db)
    assert isinstance(case.facts[0], CaseFact)
    assert case.fact_dict()["order_id"] == "BM-48213"
