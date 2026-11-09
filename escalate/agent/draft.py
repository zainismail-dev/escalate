"""Draft a step's message: fill the template with facts, then let the smart model polish it."""

import json
import logging
import re
from datetime import date

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from escalate.agent.fact_check import plain_typography
from escalate.db.events import log_event
from escalate.db.models import Case, CaseStatus, Message
from escalate.i18n.formatting import format_date, locale_for
from escalate.llm import LLM, get_llm
from escalate.llm.prompts import render_prompt
from escalate.llm.structured import StructuredOutputError, ask_json
from escalate.pii import mask_pii
from escalate.playbooks.models import Playbook, Step
from escalate.templates_engine import Rendered, disclaimer, render_step

OPEN_DRAFT = ("draft",)

log = logging.getLogger("uvicorn.error")
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


class DraftOut(BaseModel):
    subject: str
    body: str


def history(case: Case, limit: int = 6) -> str:
    msgs = [m for m in case.messages if m.status in ("sent", "received")]
    if not msgs:
        return "(none)"
    lines = []
    for m in msgs[-limit:]:
        when = (m.sent_at or m.created_at).date().isoformat()
        who = "consumer" if m.direction == "out" else "company"
        lines.append(f"- {when} {who}: {m.subject or ''} :: {m.body[:300].strip()}")
    return "\n".join(lines)


def spell_out_dates(text: str, locale: str) -> str:
    """A letter never shows 2026-10-01: always the locale's long format ("1 October 2026")."""
    return _ISO_DATE.sub(lambda m: format_date(m.group(0), locale), text)


def polish(
    llm: LLM,
    case: Case,
    step: Step,
    rendered: Rendered,
    facts: dict[str, str],
    feedback: list[str] | None,
) -> Rendered:
    fb = ""
    if feedback:
        fb = "Fix these problems from the last draft:\n" + "\n".join(f"- {x}" for x in feedback)
    locale = locale_for(case.language, case.country)
    readable = {k: spell_out_dates(v, locale) for k, v in facts.items()}
    prompt = render_prompt(
        "draft",
        step_name=step.title,
        recipient_role=step.recipient_role or "the company",
        template_subject=rendered.subject,
        template_rendered=f"\n{rendered.body}\n",
        facts_json=json.dumps(readable, ensure_ascii=False),
        history=history(case),
        language=case.language,
        feedback=fb,
    )
    out = ask_json(llm, prompt, DraftOut, slot="smart")
    if not out.body.strip():
        return rendered
    subject = plain_typography(out.subject.strip()) or rendered.subject
    body = without_subject(plain_typography(out.body.strip()), subject)
    return Rendered(subject, body + "\n")


_MARKUP = re.compile(r"^[#*_\s]+|[*_\s]+$")
_SUBJECT_LINE = re.compile(r"^(subject|re)\s*:", re.IGNORECASE)


def without_subject(body: str, subject: str) -> str:
    """The subject is shown once, as the email subject or the PDF heading. A model sometimes
    repeats it at the top of the body ("SUBJECT: ...", "**Subject:** ..." or the bare subject as
    a heading): those lines go, and the body starts at the greeting."""
    lines = body.strip("\n").split("\n")
    wanted = _MARKUP.sub("", subject).casefold()
    while lines:
        first = _MARKUP.sub("", lines[0]).strip()
        if not first or _SUBJECT_LINE.match(first) or (wanted and first.casefold() == wanted):
            lines.pop(0)
            continue
        break
    return "\n".join(lines)


def draft_step(
    session: Session,
    case: Case,
    pb: Playbook,
    step: Step,
    llm: LLM | None = None,
    feedback: list[str] | None = None,
    late: bool = False,
    today: date | None = None,
    use_llm: bool = True,
) -> Message:
    """Create a `draft` Message for this step. Raises MissingFacts if facts are missing."""
    facts = case.fact_dict()
    rendered = render_step(
        pb, step, facts, case.language, today=today, late=late, country=case.country
    )
    final = rendered
    if use_llm:
        try:
            final = polish(llm or get_llm(), case, step, rendered, facts, feedback)
        except StructuredOutputError as exc:
            final = rendered  # the filled template is already facts-only
            log.warning("draft: using the template for case %s: %s", case.id, exc.category)
            log_event(session, case.id, "draft_template_used", {"reason": exc.category})
    locale = locale_for(case.language, case.country)
    final = Rendered(spell_out_dates(final.subject, locale), spell_out_dates(final.body, locale))
    note = disclaimer(case.language, pb.generic)
    body = final.body if note in final.body else f"{final.body.rstrip()}\n\n{note}\n"

    for old in session.scalars(
        select(Message).where(
            Message.case_id == case.id, Message.step_id == step.id, Message.status == "draft"
        )
    ):
        old.status = "superseded"

    msg = Message(
        case_id=case.id,
        step_id=step.id,
        direction="out",
        channel=step.channel,
        recipient=facts.get(step.recipient_fact) if step.recipient_fact else None,
        subject=mask_pii(final.subject),
        body=mask_pii(body),
        original_body=mask_pii(f"{final.subject}\n{body}"),
        status="draft",
    )
    session.add(msg)
    case.messages.append(msg)
    case.current_step = step.id
    case.status = CaseStatus.AWAITING_APPROVAL
    session.flush()
    log_event(session, case.id, "draft_created", {"message_id": msg.id, "step": step.id})
    return msg


def template_text(
    case: Case, pb: Playbook, step: Step, late: bool = False, today: date | None = None
) -> str:
    """The trusted, facts-only rendering, used by the fact check as the allowed reference."""
    r = render_step(
        pb, step, case.fact_dict(), case.language, today=today, late=late, country=case.country
    )
    locale = locale_for(case.language, case.country)
    r = Rendered(spell_out_dates(r.subject, locale), spell_out_dates(r.body, locale))
    return f"{r.subject}\n{r.body}\n{disclaimer(case.language, pb.generic)}"
