from datetime import date

import pytest
from sqlalchemy.orm import Session

from escalate.agent.approval import (
    ApprovalError,
    UnsupportedFacts,
    approve_message,
    edit_message,
    reject_message,
)
from escalate.agent.draft import draft_step, template_text
from escalate.agent.fact_check import code_check, fact_check, find_dates, find_ids, norm_number
from escalate.channels.gate import NotApproved, require_approval
from escalate.db.models import Message, utcnow
from escalate.playbooks.loader import get_playbook
from tests.factories import LED_FACTS, led_case
from tests.fakes.fake_llm import FakeLLM

# --- fact check ------------------------------------------------------------------


def test_parsers() -> None:
    assert norm_number("45,000.00") == "45000"
    assert norm_number("4.500,00") == "4500"
    assert norm_number("45 000") == "45000"
    assert find_ids("order BM-48213 and ML-7781-SB") == {"BM-48213", "ML-7781-SB"}
    assert find_dates("on 4 November 2026, November 5, 2026, 2026-02-14 and 06/03/2026") == {
        date(2026, 11, 4),
        date(2026, 11, 5),
        date(2026, 2, 14),
        date(2026, 3, 6),
    }


def test_invented_amount_is_caught() -> None:
    draft = "You owe me PKR 50,000.00 for order BM-48213 bought on 2026-02-14."
    issues = code_check(draft, LED_FACTS)
    assert issues == ["number 50000 is not in the case facts"]


def test_invented_date_and_id_are_caught() -> None:
    draft = "Order BM-99999 placed on 1 January 2026."
    issues = code_check(draft, LED_FACTS)
    assert "date 2026-01-01 is not in the case facts" in issues
    assert "ID BM-99999 is not in the case facts" in issues


def test_formatted_fact_values_pass() -> None:
    draft = (
        "On 14 February 2026 I paid PKR 45,000.00 for order BM-48213. "
        "The TV broke after 10 days. Tracking 7731990."
    )
    assert code_check(draft, LED_FACTS) == []


def test_reference_values_pass() -> None:
    draft = "Please reply by 4 November 2026."
    assert code_check(draft, LED_FACTS) != []
    assert code_check(draft, LED_FACTS, reference="Please do this by 4 November 2026.") == []


def test_template_rendering_passes_its_own_check(db: Session) -> None:
    case = led_case(db)
    pb = get_playbook("intl-generic-refund-refused")
    for step_id in ("s1_written_demand", "s2_final_notice", "s4_small_claims"):
        text = template_text(case, pb, pb.step(step_id))
        assert (
            code_check(text, LED_FACTS, reference=template_text(case, pb, pb.step(step_id))) == []
        )


def test_model_check_runs_after_code_check() -> None:
    llm = FakeLLM(script=[{"unsupported": ["the seller admitted fault"]}])
    result = fact_check("Order BM-48213. The seller admitted fault.", LED_FACTS, llm=llm)
    assert not result.ok
    assert result.model_issues == ["the seller admitted fault"]
    assert llm.calls[0][1] == "fast"


def test_model_check_skipped_when_code_fails() -> None:
    llm = FakeLLM()
    result = fact_check("Pay 99999 now.", LED_FACTS, llm=llm)
    assert result.code_issues and llm.calls == []


# --- gate --------------------------------------------------------------------------


def _draft(db: Session) -> Message:
    case = led_case(db)
    pb = get_playbook("intl-generic-refund-refused")
    return draft_step(db, case, pb, pb.steps[0], use_llm=False)


def test_gate_blocks_draft(db: Session) -> None:
    with pytest.raises(NotApproved, match="not approved"):
        require_approval(_draft(db))


def test_gate_blocks_rejected(db: Session) -> None:
    msg = _draft(db)
    reject_message(db, msg.id, "too harsh")
    with pytest.raises(NotApproved):
        require_approval(msg)


def test_gate_blocks_status_without_timestamp(db: Session) -> None:
    msg = _draft(db)
    msg.status = "approved"  # approved_at never set: still blocked
    with pytest.raises(NotApproved):
        require_approval(msg)


def test_gate_blocks_already_sent(db: Session) -> None:
    msg = approve_message(db, _draft(db).id)
    require_approval(msg)  # passes once
    msg.sent_at = utcnow()
    with pytest.raises(NotApproved, match="already sent"):
        require_approval(msg)


def test_approve_sets_approved_at_and_logs(db: Session) -> None:
    msg = approve_message(db, _draft(db).id)
    assert msg.status == "approved"
    assert msg.approved_at is not None
    assert msg.case.events[-1].type == "message_approved"
    assert msg.case.events[-1].payload["message_id"] == msg.id


def test_cannot_approve_twice_or_after_reject(db: Session) -> None:
    msg = _draft(db)
    approve_message(db, msg.id)
    with pytest.raises(ApprovalError):
        approve_message(db, msg.id)
    other = _draft(db)
    reject_message(db, other.id, "no")
    with pytest.raises(ApprovalError):
        approve_message(db, other.id)


def test_reject_records_reason(db: Session) -> None:
    msg = reject_message(db, _draft(db).id, "  mention the warranty  ")
    assert msg.status == "rejected"
    assert msg.rejection_reason == "mention the warranty"
    assert msg.approved_at is None
    assert msg.case.events[-1].type == "message_rejected"


def test_approve_with_invented_amount_in_edit_is_blocked(db: Session) -> None:
    msg = _draft(db)
    with pytest.raises(UnsupportedFacts) as err:
        approve_message(db, msg.id, edited_body=msg.body + "\nAlso pay me 99,000.")
    assert err.value.issues == ["number 99000 is not in the case facts"]
    assert msg.approved_at is None


def test_approve_with_clean_edit(db: Session) -> None:
    msg = _draft(db)
    new = msg.body.replace("Yours sincerely", "Kind regards")
    approved = approve_message(db, msg.id, edited_body=new)
    assert "Kind regards" in approved.body
    assert [e.type for e in approved.case.events][-2:] == ["draft_edited", "message_approved"]


def test_edit_returns_warnings_but_keeps_draft(db: Session) -> None:
    msg = _draft(db)
    warnings = edit_message(db, msg.id, msg.body + "\nPaid 12345.")
    assert warnings == ["number 12345 is not in the case facts"]
    assert msg.status == "draft"


def test_only_approve_message_sets_approved_at() -> None:
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1] / "escalate"
    hits = [
        (p.relative_to(root), line.strip())
        for p in root.rglob("*.py")
        for line in p.read_text().splitlines()
        if re.search(r"\bapproved_at\s*=[^=]", line)
    ]
    assert [str(p) for p, _ in hits] == ["agent/approval.py"], hits
