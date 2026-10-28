"""Case-file PDF (section 9): cover, facts with sources, dated timeline, messages, evidence.

Jinja2 HTML -> WeasyPrint. `build_case_html` is separate so it can be checked without the PDF
system libraries.
"""

import base64
import io
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from escalate.agent.titles import display_title
from escalate.db.models import Case, Evidence, utcnow
from escalate.evidence.store import load_plain
from escalate.export.pdf import html_to_pdf
from escalate.i18n.formatting import format_money, locale_for
from escalate.templates_engine import disclaimer

THUMB_PX = 360


_env = Environment(
    loader=FileSystemLoader(str(Path(__file__).parent)),
    autoescape=select_autoescape(["html", "html.j2"], default=True),
)
_template = _env.get_template("case.html.j2")

# Event details worth showing in the timeline (never the free text of a payload).
_DETAIL_KEYS = (
    "step",
    "to",
    "channel",
    "verdict",
    "reason",
    "deadline",
    "due",
    "days_left",
    "filename",
    "playbook",
    "how",
)


def describe(event: Any) -> str:
    p = event.payload or {}
    return ", ".join(f"{k}: {p[k]}" for k in _DETAIL_KEYS if p.get(k) not in (None, ""))


def _thumbnail(ev: Evidence) -> str | None:
    if ev.kind != "image":
        return None
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(load_plain(ev)))
        img.thumbnail((THUMB_PX, THUMB_PX))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=80)
    except Exception:  # unreadable image or missing key: show the hash only
        return None
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def build_case_html(session: Session, case: Case) -> str:
    session.refresh(case)
    facts = case.fact_dict()
    currency = case.currency or facts.get("currency")
    amount_raw = facts.get("amount") or (str(case.amount) if case.amount is not None else None)
    amount = (
        format_money(amount_raw, currency, locale_for(case.language, case.country))
        if amount_raw
        else "—"
    )
    evidence = [
        {
            "id": ev.id,
            "filename": ev.filename,
            "kind": ev.kind,
            "uploaded_at": ev.uploaded_at,
            "sha256": ev.sha256,
            "thumb": _thumbnail(ev),
            "excerpt": (ev.extracted_text or "")[:200],
        }
        for ev in case.evidence
    ]
    messages = [m for m in case.messages if m.status in ("sent", "received", "approved")]
    generic = bool(case.playbook_id and case.playbook_id.startswith("intl-"))
    return _template.render(
        case=case,
        title=display_title(case),
        facts=facts,
        amount=amount,
        evidence=evidence,
        evidence_names={ev.id: ev.filename for ev in case.evidence},
        messages=messages,
        describe=describe,
        notice=disclaimer(case.language, generic).lstrip("-").strip(),
        generated=utcnow().strftime("%Y-%m-%d %H:%M"),
        rtl={"ur", "ar", "fa", "he"},
    )


def build_case_pdf(session: Session, case: Case) -> bytes:
    return html_to_pdf(build_case_html(session, case))
