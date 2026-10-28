"""Draft review endpoints. Approval goes through the runner -> approve_message (the only place
that sets approved_at) -> graph `send`."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from escalate.agent import runner
from escalate.agent.approval import edit_message
from escalate.api.deps import get_message, get_session
from escalate.api.routes.cases import run_out
from escalate.api.schemas import (
    ApproveIn,
    DeliveryIn,
    EditOut,
    MessageEdit,
    MessageOut,
    RejectIn,
    RunOut,
)
from escalate.export.pdf import letter_pdf

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
def approve(
    message_id: int, body: ApproveIn | None = None, session: Session = Depends(get_session)
) -> RunOut:
    case_id = _pending_case(session, message_id, "approve_draft")
    b = body or ApproveIn()
    return run_out(runner.resume_with_decision(case_id, "approve", b.body, b.subject))


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
