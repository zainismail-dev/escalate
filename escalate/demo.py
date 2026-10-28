"""Four demo cases in four countries, run through the real agent graph with a scripted offline
model. Nothing is sent: each case stops where it needs the user (approve a draft, or the scam
checklist). All names, companies and addresses are fictional (`.example` domains).

    uv run python -m escalate.demo        # or POST /demo/seed, or `make demo-data`
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

from escalate import llm as llm_module
from escalate.agent import runner
from escalate.agent.approval import edit_message
from escalate.db.events import log_event
from escalate.db.models import Case, CaseFact, Message
from escalate.db.session import session_scope
from escalate.evidence.store import save_upload
from escalate.i18n.countries import currency_for
from escalate.llm import set_llm
from escalate.llm.client import Slot


@dataclass
class DemoCase:
    marker: str  # unique text in the description, so the scripted model knows the case
    country: str
    region: str | None
    language: str
    case_type: str
    description: str
    evidence_name: str
    evidence_text: str
    facts: dict[str, str]
    blank: str | None = None  # a `[[...]]` line added to the draft, to show blanks
    extra: dict[str, Any] = field(default_factory=dict)


CASES = [
    DemoCase(
        marker="BM-48213",
        country="PK",
        region="PK-SD",
        language="en",
        case_type="refund_refused",
        description=(
            "I bought an LED TV from BrightMart Electronics through ShopNow (order BM-48213) for "
            "Rs 64,500. It stopped working after 10 days. I sent it back, and for months they "
            "keep saying they will replace it when the company approves the claim."
        ),
        evidence_name="brightmart-invoice.txt",
        evidence_text=(
            "BrightMart Electronics - Tax invoice\nOrder: BM-48213\nDate: 2026-02-14\n"
            "Item: 43-inch LED TV\nTotal paid: PKR 64,500\nSold via ShopNow Marketplace\n"
        ),
        facts={
            "buyer_name": "Ayesha Siddiqui",
            "seller_name": "BrightMart Electronics",
            "seller_contact": "support@brightmart.example",
            "order_id": "BM-48213",
            "order_date": "2026-02-14",
            "amount": "64500",
            "currency": "PKR",
            "defect_description": (
                "The LED TV stopped working after 10 days: no picture, only sound."
            ),
            "remedy_wanted": "a replacement LED TV or a full refund",
            "platform_name": "ShopNow Marketplace",
            "return_shipped_on": "2026-02-28",
        },
    ),
    DemoCase(
        marker="UPI-5521907",
        country="IN",
        region=None,
        language="en",
        case_type="scam",
        description=(
            "Someone called saying a parcel for me was stuck at customs and I had to pay a fee. "
            "I paid ₹18,000 by UPI (reference UPI-5521907) and the number stopped answering."
        ),
        evidence_name="upi-payment-screenshot.txt",
        evidence_text=(
            "Payment successful\nAmount: INR 18,000\nUPI ref: UPI-5521907\nDate: 2026-10-26\n"
        ),
        facts={
            "buyer_name": "Rohan Mehta",
            "amount": "18000",
            "currency": "INR",
            "paid_on": "2026-10-26",
            "payment_method": "UPI transfer",
            "transaction_id": "UPI-5521907",
            "scam_description": (
                "A caller claimed to be from a courier and asked for a customs fee."
            ),
        },
    ),
    DemoCase(
        marker="PF-220931",
        country="GB",
        region=None,
        language="en-GB",
        case_type="subscription_cancel",
        description=(
            "I cancelled my PulseFit gym membership (member PF-220931) on 31 August, but they "
            "keep taking £39.99 every month and say I must visit in person."
        ),
        evidence_name="pulsefit-cancellation-email.txt",
        evidence_text=(
            "To: members@pulsefit.example\nDate: 2026-08-31\nSubject: Cancel membership PF-220931"
            "\nPlease cancel my monthly membership (GBP 39.99 per month) from today.\n"
        ),
        facts={
            "buyer_name": "Sam Taylor",
            "company_name": "PulseFit Gyms",
            "company_contact": "members@pulsefit.example",
            "account_id": "PF-220931",
            "cancel_requested_on": "2026-08-31",
            "remedy_wanted": "confirm the cancellation and refund every charge after 31 August",
            "plan_name": "monthly membership",
            "amount": "39.99",
            "currency": "GBP",
        },
    ),
    DemoCase(
        marker="NL-77120",
        country="US",
        region="US-CA",
        language="en-US",
        case_type="refund_refused",
        description=(
            "I bought a laptop from Northline Computers (order NL-77120) for $1,249.00. The "
            "screen flickers and goes black. They refuse a refund and only offer store credit."
        ),
        evidence_name="northline-receipt.txt",
        evidence_text=(
            "Northline Computers\nOrder NL-77120\nDate: 2026-09-05\nLaptop 14-inch\n"
            "Total: USD 1,249.00\n"
        ),
        facts={
            "buyer_name": "Jordan Lee",
            "seller_name": "Northline Computers",
            "seller_contact": "help@northline.example",
            "order_id": "NL-77120",
            "order_date": "2026-09-05",
            "amount": "1249.00",
            "currency": "USD",
            "defect_description": "The screen flickers and goes black within minutes of use.",
            "remedy_wanted": "a full refund to my card",
        },
        blank="My phone number: [[your phone number]]",
    ),
]


class DemoLLM:
    """Answers the agent's prompts from the demo facts. Drafts are the filled templates."""

    def __init__(self, cases: list[DemoCase]) -> None:
        self.cases = cases

    def _case(self, prompt: str) -> DemoCase:
        return next((c for c in self.cases if c.marker in prompt), self.cases[0])

    def complete(self, prompt: str, slot: Slot = "smart") -> str:
        if "You extract facts" in prompt:
            ev = re.search(r"\[evidence_id=(\d+)\]", prompt)
            eid = int(ev.group(1)) if ev else None
            facts = self._case(prompt).facts
            return json.dumps(
                {
                    "facts": {
                        k: {"value": v, "evidence_id": eid, "confidence": 0.95}
                        for k, v in facts.items()
                    }
                }
            )
        if "Classify this complaint" in prompt:
            c = self._case(prompt)
            return json.dumps(
                {
                    "case_type": c.case_type,
                    "country": c.country,
                    "region": c.region,
                    "language": "en",
                    "urgent": c.case_type == "scam",
                    "reason": "demo case",
                }
            )
        if "You write the" in prompt:
            block = prompt.split("keep its structure:", 1)[1].split("Facts you may use", 1)[0]
            m = re.search(r"SUBJECT: (.*)\n", block)
            body = block.split("\n", 2)[2] if m else block
            return json.dumps({"subject": m.group(1) if m else "", "body": body.strip()})
        if "List every factual claim" in prompt:
            return json.dumps({"unsupported": []})
        if "A company replied" in prompt:
            return json.dumps({"verdict": "refused", "reason": "demo"})
        raise ValueError("the demo model has no reply for this prompt")


def _create(c: DemoCase) -> int:
    with session_scope() as s:
        case = Case(
            description=c.description,
            country=c.country,
            region=c.region,
            language=c.language,
            currency=currency_for(c.country),
        )
        s.add(case)
        s.flush()
        log_event(s, case.id, "case_created", {"country": c.country, "region": c.region})
        log_event(s, case.id, "demo_case", {})
        ev = save_upload(s, case.id, c.evidence_name, c.evidence_text.encode())
        if c.case_type == "scam":
            # Scam cases show the checklist before any extraction; store the facts now.
            for k, v in c.facts.items():
                s.add(CaseFact(case_id=case.id, key=k, value=v, source_evidence_id=ev.id))
        return case.id


def seed(cases: list[DemoCase] | None = None) -> list[int]:
    cases = cases or CASES
    ids = []
    with runner._lock:  # no real case runs while the demo model is plugged in
        previous = llm_module._llm
        set_llm(DemoLLM(cases))
        try:
            for c in cases:
                cid = _create(c)
                result = runner.start_case(cid)
                if c.blank and result.waiting_for == "approve_draft" and result.pending:
                    msg_id = int(result.pending["draft"]["message_id"])
                    with session_scope() as s:
                        body = s.get_one(Message, msg_id).body
                        head, sep, notice = body.rpartition("\n---")
                        new = f"{head.rstrip()}\n\n{c.blank}\n{sep}{notice}" if sep else body
                        edit_message(s, msg_id, new)
                ids.append(cid)
        finally:
            set_llm(previous)
    return ids


if __name__ == "__main__":
    from escalate.api.main import init_db

    init_db()
    runner.configure()
    print("demo cases:", seed())
