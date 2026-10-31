"""Hosted mode: the signed-in user's account. Open to everyone signed in (the waitlist and
consent pages need it); nothing is stored about users who aren't invited."""

from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from escalate.api.deps import get_session, identity
from escalate.api.schemas import ConfirmIn
from escalate.config import get_settings
from escalate.db import repo
from escalate.db.models import User, utcnow
from escalate.hosted import lifecycle
from escalate.hosted.accounts import is_invited, record_consent
from escalate.llm.quota import calls_today

router = APIRouter(prefix="/me", tags=["account"])


class MeOut(BaseModel):
    email: str
    invited: bool
    consented: bool
    open_cases: int = 0
    max_open_cases: int
    ai_calls_today: int = 0
    ai_calls_per_day: int


class DeleteIn(BaseModel):
    """The user typed DELETE."""

    confirm: Literal["DELETE"]


def me_out(session: Session, request: Request) -> MeOut:
    ident, s = identity(request), get_settings()
    invited = is_invited(session, ident.email)
    user = session.get(User, ident.user_id) if invited else None
    out = MeOut(
        email=ident.email,
        invited=invited,
        consented=bool(user and user.consented_at),
        max_open_cases=s.max_open_cases,
        ai_calls_per_day=s.ai_calls_per_day,
    )
    if user is not None:
        out.open_cases = repo.open_case_count(session)
        out.ai_calls_today = calls_today(session, ident.user_id)
    return out


@router.get("", response_model=MeOut)
def me(request: Request, session: Session = Depends(get_session)) -> MeOut:
    return me_out(session, request)


@router.post("/consent", response_model=MeOut)
def consent(body: ConfirmIn, request: Request, session: Session = Depends(get_session)) -> MeOut:
    """The first-run consent: AI processing by the hosted provider, not legal advice, own case
    data only, beta. 403 waitlist for people who aren't invited."""
    record_consent(session, identity(request))
    session.commit()
    return me_out(session, request)


@router.get("/export")
def export(request: Request, session: Session = Depends(get_session)) -> StreamingResponse:
    """A zip of everything: data.json, each case's PDF and the original evidence files."""
    ident = identity(request)
    record = lifecycle.export_data(session, ident)
    name = f"escalate-export-{utcnow():%Y%m%d}.zip"
    return StreamingResponse(
        iter(lambda: record.read(64 * 1024), b""),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.post("/delete", status_code=204)
def delete_account(body: DeleteIn, request: Request) -> Response:
    """Delete the account: every case, evidence file, checkpoint, setting and the sign-in."""
    lifecycle.delete_account(identity(request))
    return Response(status_code=204)
