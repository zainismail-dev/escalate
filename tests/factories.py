"""Shared test data: the broken-LED case from the build plan."""

from sqlalchemy.orm import Session

from escalate.db.models import Case, CaseFact

LED_TEXT = (
    "My name is Ali Raza. On 14 February 2026 I bought a 43 inch LED TV from BrightMart "
    "Electronics (order BM-48213) for Rs 45,000. It stopped working after 10 days. I returned "
    "it on 2026-02-28. For 8 months they say they will replace it when the company claim is "
    "approved. I want a replacement or a full refund."
)

LED_FACTS = {
    "buyer_name": "Ali Raza",
    "seller_name": "BrightMart Electronics",
    "seller_contact": "support@brightmart.example",
    "order_id": "BM-48213",
    "order_date": "2026-02-14",
    "amount": "45000",
    "currency": "PKR",
    "defect_description": "The LED TV stopped working after 10 days: no picture, only sound.",
    "remedy_wanted": "a replacement LED TV or a full refund",
    "return_shipped_on": "2026-02-28",
    "return_tracking": "7731990",
    "last_promise_on": "2026-09-30",
    "last_promise_text": "we will replace it when the company claim is approved",
}


def led_case(db: Session, with_facts: bool = True, **kw: object) -> Case:
    fields: dict[str, object] = {
        "description": LED_TEXT,
        "country": "PK",
        "region": "PK-SD",
        "case_type": "refund_refused",
        "language": "en",
    }
    fields.update(kw)
    case = Case(**fields)
    db.add(case)
    db.flush()
    if with_facts:
        for k, v in LED_FACTS.items():
            db.add(CaseFact(case_id=case.id, key=k, value=v))
    db.flush()
    db.refresh(case)
    return case


# What the web app sends: an allowed Origin and the anti-CSRF header, to a trusted Host.
APP_ORIGIN = "http://localhost:3000"
APP_HEADERS = {"Origin": APP_ORIGIN, "X-Escalate-Request": "1"}
APP_BASE_URL = "http://localhost"
