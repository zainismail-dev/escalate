"""Draft review endpoints. Approval goes through the runner -> approve_message (the only place
that sets approved_at) -> graph `send`."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from escalate.agent import review as rv
from escalate.agent import runner
from escalate.agent.approval import approved_text, edit_message, same_recipient
from escalate.agent.intake import save_answers
from escalate.api.deps import get_message, get_session
from escalate.api.routes.cases import run_out
from escalate.api.schemas import (
    ApproveIn,
    CheckOut,
    DeliveryIn,
    EditOut,
    MessageEdit,
    MessageOut,
    PreviewOut,
    ProblemOut,
    RecipientCheckOut,
    RecipientIn,
    RejectIn,
    ReviewFactOut,
    ReviewOut,
    RunOut,
    SegmentOut,
)
from escalate.channels.email_smtp import EMAIL_RE
from escalate.config import get_settings
from escalate.db.events import log_event
from escalate.db.models import Message
from escalate.export.pdf import letter_pdf
from escalate.i18n.countries import is_rtl, letter_language, primary_language
from escalate.i18n.formatting import locale_for
from escalate.playbooks.loader import get_playbook
from escalate.playbooks.models import template_languages
from escalate.templates_engine import MissingFacts, MissingPlaceholder, disclaimer, render_step

router = APIRouter(prefix="/messages", tags=["messages"])


def _pending_case(session: Session, message_id: int, kind: str) -> int:
    msg = get_message(session, message_id)
    case_id = msg.case_id
    p = runner.pending(case_id)
    key = "draft" if kind == "approve_draft" else None
    pending_id = (p or {}).get(key, {}).get("message_id") if key else (p or {}).get("message_id")
    if not p or p.get("type") != kind or pending_id != message_id:
        raise HTTPException(409, f"message {message_id} is not waiting for {kind}")
    session.close()
    return case_id


@router.put("/{message_id}", response_model=EditOut)
def edit(message_id: int, body: MessageEdit, session: Session = Depends(get_session)) -> EditOut:
    warnings = edit_message(session, message_id, body.body, body.subject)
    session.commit()
    return EditOut(
        message=MessageOut.model_validate(get_message(session, message_id)), warnings=warnings
    )


@router.post("/{message_id}/approve", response_model=RunOut)
def approve(message_id: int, body: ApproveIn, session: Session = Depends(get_session)) -> RunOut:
    """Body: {"confirm": true, "recipient": "<the address the user checked>"}. Approving sends."""
    case_id = _pending_case(session, message_id, "approve_draft")
    return run_out(
        runner.resume_with_decision(
            case_id, "approve", body.body, body.subject, recipient=body.recipient
        )
    )


def _recipient_fact(case_playbook_id: str | None, step_id: str) -> str | None:
    if not case_playbook_id:
        return None
    pb = get_playbook(case_playbook_id)
    ids = {s.id for s in pb.steps}
    return pb.step(step_id).recipient_fact if step_id in ids else None


@router.post("/{message_id}/recipient", response_model=MessageOut)
def set_recipient(
    message_id: int, body: RecipientIn, session: Session = Depends(get_session)
) -> MessageOut:
    """The user corrects a draft's recipient. It becomes a fact the user provided, so
    evidence read later can't replace it."""
    msg = get_message(session, message_id)
    if msg.direction != "out" or msg.status != "draft":
        raise HTTPException(409, f"message {message_id} is not a draft")
    value = " ".join(body.recipient.split())
    if msg.channel == "email" and not EMAIL_RE.match(value):
        raise HTTPException(422, "enter a valid email address")
    msg.recipient = value
    key = _recipient_fact(msg.case.playbook_id, msg.step_id)
    if key:
        save_answers(session, msg.case, {key: value})
    log_event(session, msg.case_id, "recipient_set", {"message_id": msg.id, "fact": key})
    session.commit()
    return MessageOut.model_validate(msg)


def recipient_check(msg: Message) -> RecipientCheckOut:
    """Where the recipient came from, and whether it differs from an earlier approved letter
    for the same role (a "recipient changed" warning)."""
    case = msg.case
    key = _recipient_fact(case.playbook_id, msg.step_id)
    fact = next((f for f in case.facts if f.key == key), None) if key else None
    files = {e.id: e.filename for e in case.evidence}
    if fact is None or not same_recipient(fact.value, msg.recipient):
        source, filename = ("agent" if msg.recipient else "none"), None
    elif fact.source_evidence_id is not None:
        source, filename = "evidence", files.get(fact.source_evidence_id)
    elif fact.confidence >= 1.0:
        source, filename = "you", None
    else:
        source, filename = "agent", None
    earlier = [
        m.recipient
        for m in case.messages
        if m.approved_at
        and m.id != msg.id
        and m.recipient
        and _recipient_fact(case.playbook_id, m.step_id) == key
    ]
    previous = earlier[-1] if earlier else None
    changed = bool(previous and msg.recipient and not same_recipient(previous, msg.recipient))
    return RecipientCheckOut(
        recipient=msg.recipient,
        source=source,
        source_filename=filename,
        previous=previous,
        changed=changed,
    )


@router.post("/{message_id}/reject", response_model=RunOut)
def reject(message_id: int, body: RejectIn, session: Session = Depends(get_session)) -> RunOut:
    case_id = _pending_case(session, message_id, "approve_draft")
    return run_out(runner.resume_with_decision(case_id, "reject", reason=body.reason))


@router.post("/{message_id}/confirm-delivery", response_model=RunOut)
def confirm_delivery(
    message_id: int, body: DeliveryIn, session: Session = Depends(get_session)
) -> RunOut:
    case_id = _pending_case(session, message_id, "confirm_delivery")
    return run_out(runner.confirm_delivery(case_id, body.evidence_id))


@router.get("/{message_id}/printable.pdf")
def printable(message_id: int, session: Session = Depends(get_session)) -> Response:
    msg = get_message(session, message_id)
    pdf = letter_pdf(msg.subject, msg.body, msg.case.language)
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="letter-{message_id}.pdf"'},
    )


def _segments(text: str, displays: dict[str, list[str]]) -> list[SegmentOut]:
    return [SegmentOut(**vars(seg)) for seg in rv.segments(text, displays)]


@router.get("/{message_id}/review", response_model=ReviewOut)
def review(message_id: int, session: Session = Depends(get_session)) -> ReviewOut:
    """Everything the review screen needs: highlighted text, facts with sources, checks."""
    msg = get_message(session, message_id)
    case = msg.case
    pb = get_playbook(case.playbook_id) if case.playbook_id else None
    step = pb.step(msg.step_id) if pb and msg.step_id in {s.id for s in pb.steps} else None
    notice = disclaimer(case.language, pb.generic if pb else True)
    checks, issues = rv.checks(msg, approved_text(msg), notice)
    displays = rv.fact_displays(case)
    subject = _segments(msg.subject or "", displays)
    body = _segments(msg.body, displays)
    used = {seg.key for seg in [*subject, *body] if seg.kind == "fact"}
    files = {e.id: e.filename for e in case.evidence}
    pending = runner.pending(case.id) or {}
    waiting = (
        pending.get("type") == "approve_draft"
        and pending.get("draft", {}).get("message_id") == msg.id
    )
    blocking = {"facts", "blanks"}
    tdir = get_settings().templates_dir
    return ReviewOut(
        message=MessageOut.model_validate(msg),
        case_id=case.id,
        language=case.language,
        locale=locale_for(case.language, case.country).replace("_", "-"),
        text_direction="rtl" if is_rtl(case.language) else "ltr",
        subject_segments=subject,
        body_segments=body,
        facts=[
            ReviewFactOut(
                key=f.key,
                value=f.value,
                display=displays.get(f.key, [f.value]),
                confidence=f.confidence,
                source_evidence_id=f.source_evidence_id,
                source_filename=files.get(f.source_evidence_id or -1),
                used=f.key in used,
            )
            for f in case.facts
        ],
        blanks=rv.blanks(f"{msg.subject or ''}\n{msg.body}"),
        checks=[CheckOut(**vars(c)) for c in checks],
        problems=[ProblemOut(**vars(p)) for p in rv.problems(issues, case.fact_dict())],
        can_approve=waiting and all(c.ok for c in checks if c.id in blocking),
        template_languages=template_languages(tdir, step.template) if step else [],
        step_name=step.title if step else None,
        recipient_check=recipient_check(msg),
    )


@router.get("/{message_id}/preview", response_model=PreviewOut)
def preview(message_id: int, language: str, session: Session = Depends(get_session)) -> PreviewOut:
    """The step's template filled in another language, for the side-by-side view only. It is
    never sent: switching the letter language redrafts through the agent and the fact check."""
    try:
        tag = letter_language(language)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    msg = get_message(session, message_id)
    case = msg.case
    direction = "rtl" if is_rtl(tag) else "ltr"
    if not case.playbook_id:
        return PreviewOut(language=tag, available=False, text_direction=direction)
    pb = get_playbook(case.playbook_id)
    step = pb.step(msg.step_id)
    langs = template_languages(get_settings().templates_dir, step.template)
    if primary_language(tag) not in langs:
        return PreviewOut(language=tag, available=False, text_direction=direction)
    try:
        r = render_step(
            pb, step, case.fact_dict(), tag, today=msg.created_at.date(), country=case.country
        )
    except (MissingFacts, MissingPlaceholder):
        return PreviewOut(language=tag, available=False, text_direction=direction)
    body = f"{r.body.rstrip()}\n\n{disclaimer(tag, pb.generic)}\n"
    return PreviewOut(
        language=tag, available=True, text_direction=direction, subject=r.subject, body=body
    )
