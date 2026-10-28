"""Classify a complaint (section 8, prompt 2) and pick its playbook with the resolver."""

import re
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from escalate.db.events import log_event
from escalate.db.models import Case
from escalate.i18n.formatting import to_decimal
from escalate.llm import LLM, get_llm
from escalate.llm.prompts import render_prompt
from escalate.llm.structured import ask_json
from escalate.playbooks.models import Playbook
from escalate.playbooks.resolver import resolve

CASE_TYPES = ("refund_refused", "subscription_cancel", "scam")
_COUNTRY = re.compile(r"^[A-Z]{2}$")
_REGION = re.compile(r"^[A-Z]{2}-[A-Z0-9]{1,3}$")
_LANG = re.compile(r"^[a-z]{2}$")


class Classification(BaseModel):
    case_type: Literal["refund_refused", "subscription_cancel", "scam", "other"]
    country: str | None = None
    region: str | None = None
    language: str = "en"
    urgent: bool = False
    reason: str = ""

    @field_validator("country", "region", mode="before")
    @classmethod
    def _upper(cls, v: object) -> object:
        return v.strip().upper() or None if isinstance(v, str) else v

    @field_validator("language", mode="before")
    @classmethod
    def _lower(cls, v: object) -> object:
        return v.strip().lower()[:2] if isinstance(v, str) else v

    def cleaned(self) -> "Classification":
        """Drop anything that is not a well-formed ISO code."""
        country = self.country if self.country and _COUNTRY.match(self.country) else None
        region = self.region if self.region and _REGION.match(self.region) else None
        if region and country and not region.startswith(country + "-"):
            region = None
        language = self.language if _LANG.match(self.language) else "en"
        return self.model_copy(update={"country": country, "region": region, "language": language})


def classify_text(summary: str, llm: LLM | None = None) -> Classification:
    prompt = render_prompt("classify", summary=summary.strip())
    return ask_json(llm or get_llm(), prompt, Classification, slot="fast").cleaned()


def apply_playbook(session: Session, case: Case) -> Playbook:
    """Resolve the playbook from what the case knows now (company may come from facts)."""
    facts = case.fact_dict()
    company = case.company or facts.get("seller_name") or facts.get("company_name")
    assert case.case_type, "classify the case first"
    pb = resolve(case.country, case.region, case.case_type, company=company)
    if case.playbook_id != pb.id:
        case.playbook_id, case.playbook_version = pb.id, pb.version
        log_event(session, case.id, "playbook_selected", {"playbook": pb.id, "version": pb.version})
    if facts.get("currency") and not case.currency:
        case.currency = facts["currency"].strip().upper()[:3]
    amount: Decimal | None = to_decimal(facts["amount"]) if facts.get("amount") else None
    if amount is not None:
        case.amount = amount
    if company and not case.company:
        case.company = company
    return pb


def classify(session: Session, case: Case, llm: LLM | None = None) -> Classification:
    """Classify the case text; the user's own country/region choice always wins."""
    result = classify_text(case.description, llm)
    case_type = result.case_type if result.case_type in CASE_TYPES else "refund_refused"
    case.case_type = case.case_type or case_type
    case.country = case.country or result.country
    case.region = case.region or result.region
    if case.region and case.country and not case.region.startswith(case.country + "-"):
        case.region = None
    log_event(
        session,
        case.id,
        "classified",
        {
            "case_type": case.case_type,
            "model_case_type": result.case_type,
            "country": case.country,
            "region": case.region,
            "text_language": result.language,
            "urgent": result.urgent,
            "reason": result.reason,
        },
    )
    apply_playbook(session, case)
    session.flush()
    return result
