"""Draft a step's message: fill the template with facts, then let the smart model polish it."""

import json
from datetime import date

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from escalate.db.events import log_event
from escalate.db.models import Case, CaseStatus, Message
from escalate.llm import LLM, get_llm
from escalate.llm.prompts import render_prompt
from escalate.llm.structured import StructuredOutputError, ask_json
from escalate.pii import mask_pii
from escalate.playbooks.models import Playbook, Step
from escalate.templates_engine import Rendered, disclaimer, render_step

OPEN_DRAFT = ("draft",)


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
    prompt = render_prompt(
        "draft",
        step_name=step.title,
        recipient_role=step.recipient_role or "the company",
        template_rendered=f"\nSUBJECT: {rendered.subject}\n{rendered.body}\n",
        facts_json=json.dumps(facts, ensure_ascii=False),
        history=history(case),
        language=case.language,
        feedback=fb,
    )
    out = ask_json(llm, prompt, DraftOut, slot="smart")
    if not out.body.strip():
        return rendered
    return Rendered(out.subject.strip() or rendered.subject, out.body.strip() + "\n")


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
        except StructuredOutputError:
            final = rendered  # the filled template is already facts-only
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
    return f"{r.subject}\n{r.body}\n{disclaimer(case.language, pb.generic)}"
