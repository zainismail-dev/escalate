"""Human case titles from facts, with a fixed template per case type (no model, nothing invented).

"LED TV — refund refused", "Monthly membership still charging after cancelling",
"Scam payment by UPI transfer". The user can rename a case; their title is never overwritten.
"""

from sqlalchemy.orm import Session

from escalate.db.events import log_event
from escalate.db.models import Case

MAX_PART = 60
MAX_TITLE = 120


def _short(text: str, limit: int = MAX_PART) -> str:
    text = " ".join(text.split()).rstrip(".")
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def auto_title(case_type: str | None, facts: dict[str, str], company: str | None = None) -> str:
    def f(*keys: str) -> str | None:
        for k in keys:
            v = (facts.get(k) or "").strip()
            if v:
                return _short(v)
        return None

    if case_type == "refund_refused":
        if product := f("product"):
            return _cap(f"{product} — refund refused")
        seller = f("seller_name") or company
        return f"Refund refused by {seller}" if seller else "Refund refused"
    if case_type == "subscription_cancel":
        what = f("plan_name", "company_name") or company
        if what:
            return _cap(f"{what} still charging after cancelling")
        return "Subscription still charging after cancelling"
    if case_type == "scam":
        if method := f("payment_method"):
            return f"Scam payment by {method}"
        if scammer := f("scammer_name"):
            return f"Scam payment to {scammer}"
        return "Suspected scam payment"
    return f"Complaint about {company}" if company else "Consumer complaint"


def display_title(case: Case) -> str:
    """The user's (or stored) title, else one built from the current facts."""
    return case.title or auto_title(case.case_type, case.fact_dict(), case.company)


def ensure_title(session: Session, case: Case) -> None:
    """Store a title once facts are known (intake). Never replaces an existing one."""
    if case.title or not case.facts:
        return
    case.title = auto_title(case.case_type, case.fact_dict(), case.company)[:MAX_TITLE]
    log_event(session, case.id, "title_set", {"title": case.title, "by": "agent"})
