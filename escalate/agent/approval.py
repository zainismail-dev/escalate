"""Approve or reject a draft. `approve_message` is the ONLY code that sets `approved_at`."""

from sqlalchemy.orm import Session

from escalate.agent.fact_check import code_check
from escalate.db.events import log_event
from escalate.db.models import Message, utcnow
from escalate.pii import mask_pii
from escalate.safety import check_recipient


class ApprovalError(Exception):
    """The message cannot be approved or rejected in its current state."""


class UnsupportedFacts(ApprovalError):
    def __init__(self, issues: list[str]) -> None:
        super().__init__("; ".join(issues))
        self.issues = issues


def _get_draft(session: Session, message_id: int) -> Message:
    msg = session.get(Message, message_id)
    if msg is None:
        raise ApprovalError(f"message {message_id} not found")
    if msg.direction != "out" or msg.status != "draft":
        raise ApprovalError(f"message {message_id} is {msg.status}, not an outgoing draft")
    return msg


def edit_message(
    session: Session, message_id: int, body: str, subject: str | None = None
) -> list[str]:
    """Save the user's edit (still a draft). Returns code fact-check warnings for the UI."""
    msg = _get_draft(session, message_id)
    reference = _approved_text(msg)
    body, subject = mask_pii(body), mask_pii(subject) if subject is not None else None
    msg.body = body
    if subject is not None:
        msg.subject = subject
    log_event(session, msg.case_id, "draft_edited", {"message_id": msg.id})
    return code_check(f"{msg.subject or ''}\n{msg.body}", msg.case.fact_dict(), reference)


def _approved_text(msg: Message) -> str:
    """Known-good text: the fact-checked draft and anything already approved in this case."""
    approved = [f"{m.subject or ''}\n{m.body}" for m in msg.case.messages if m.approved_at]
    return "\n".join([msg.original_body or "", *approved])


def approve_message(
    session: Session,
    message_id: int,
    edited_body: str | None = None,
    edited_subject: str | None = None,
    reference: str = "",
) -> Message:
    """Approve a draft. The final text (with any edits, including earlier PUT edits) must pass
    the code fact check against the facts and the fact-checked draft."""
    msg = _get_draft(session, message_id)
    edited = edited_body is not None or edited_subject is not None
    body = mask_pii(edited_body) if edited_body is not None else msg.body
    subject = mask_pii(edited_subject) if edited_subject is not None else msg.subject
    issues = code_check(
        f"{subject or ''}\n{body}",
        msg.case.fact_dict(),
        f"{reference}\n{_approved_text(msg)}",
    )
    if issues:
        raise UnsupportedFacts(issues)
    check_recipient(session, msg)
    if edited:
        msg.body, msg.subject = body, subject
        log_event(session, msg.case_id, "draft_edited", {"message_id": msg.id})
    msg.status = "approved"
    msg.approved_at = utcnow()
    session.flush()
    log_event(session, msg.case_id, "message_approved", {"message_id": msg.id, "step": msg.step_id})
    return msg


def reject_message(session: Session, message_id: int, reason: str) -> Message:
    msg = _get_draft(session, message_id)
    msg.status = "rejected"
    msg.rejection_reason = reason.strip() or "rejected"
    session.flush()
    log_event(
        session,
        msg.case_id,
        "message_rejected",
        {"message_id": msg.id, "reason": msg.rejection_reason},
    )
    return msg
