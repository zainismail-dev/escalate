"""Case endpoints."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from escalate.agent import runner
from escalate.agent.deadlines import deadline_status
from escalate.api.deps import get_case, get_session
from escalate.api.schemas import (
    AnswersIn,
    CaseCreate,
    CaseDetail,
    CaseOut,
    DeadlineOut,
    EventOut,
    EvidenceOut,
    MessageOut,
    ReplyIn,
    ReplyOut,
    RunOut,
    WithdrawIn,
)
from escalate.config import get_settings
from escalate.db.events import log_event
from escalate.db.models import Case, CaseStatus, Event, Message
from escalate.evidence.store import save_upload
from escalate.playbooks.loader import PlaybookError, get_playbook

router = APIRouter(prefix="/cases", tags=["cases"])


def run_out(r: runner.RunResult) -> RunOut:
    return RunOut(
        case_id=r.case_id, waiting_for=r.waiting_for, pending=r.pending, warnings=r.warnings or []
    )


def case_detail(session: Session, case: Case) -> CaseDetail:
    session.refresh(case)
    detail = CaseDetail.model_validate(case)
    detail.pending = runner.pending(case.id)
    if detail.pending and detail.pending.get("type") == "approve_draft":
        msg = session.get(Message, detail.pending["draft"]["message_id"])
        detail.pending_draft = MessageOut.model_validate(msg) if msg else None
    if case.playbook_id:
        try:
            pb = get_playbook(case.playbook_id)
        except PlaybookError:
            pb = None
        if pb is not None:
            detail.generic_playbook = pb.generic
            detail.deadlines = [DeadlineOut(**vars(d)) for d in deadline_status(case, pb)]
            if case.current_step:
                detail.step_name = pb.step(case.current_step).title
    return detail


@router.post("", response_model=CaseDetail, status_code=201)
def create_case(body: CaseCreate, session: Session = Depends(get_session)) -> CaseDetail:
    settings = get_settings()
    case = Case(
        description=body.description.strip(),
        country=body.country or settings.default_country,
        region=body.region,
        language=body.language,
        company=body.company,
    )
    if case.region and case.country and not case.region.startswith(case.country + "-"):
        raise HTTPException(422, f"region {case.region} is not in country {case.country}")
    session.add(case)
    session.flush()
    log_event(session, case.id, "case_created", {"country": case.country, "region": case.region})
    session.commit()
    if body.start:
        runner.start_case(case.id)
    return case_detail(session, case)


@router.get("", response_model=list[CaseOut])
def list_cases(status: str | None = None, session: Session = Depends(get_session)) -> list[CaseOut]:
    q = select(Case).order_by(Case.id.desc())
    if status:
        q = q.where(Case.status == status)
    return [CaseOut.model_validate(c) for c in session.scalars(q)]


@router.get("/{case_id}", response_model=CaseDetail)
def read_case(case_id: int, session: Session = Depends(get_session)) -> CaseDetail:
    return case_detail(session, get_case(session, case_id))


@router.post("/{case_id}/evidence", response_model=EvidenceOut, status_code=201)
async def upload_evidence(
    case_id: int, file: UploadFile = File(...), session: Session = Depends(get_session)
) -> EvidenceOut:
    get_case(session, case_id)
    settings = get_settings()
    limit = settings.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"file is larger than {settings.max_upload_mb} MB")
    if not data:
        raise HTTPException(422, "empty file")
    ev = save_upload(session, case_id, file.filename or "upload", data)
    session.commit()
    return EvidenceOut.model_validate(ev)


@router.post("/{case_id}/start", response_model=RunOut)
def start(case_id: int, session: Session = Depends(get_session)) -> RunOut:
    get_case(session, case_id)
    session.close()
    if runner.pending(case_id) is not None:
        raise HTTPException(409, "case already started")
    return run_out(runner.start_case(case_id))


@router.post("/{case_id}/answers", response_model=RunOut)
def answers(case_id: int, body: AnswersIn, session: Session = Depends(get_session)) -> RunOut:
    get_case(session, case_id)
    session.close()
    return run_out(runner.resume_with_answers(case_id, body.answers))


@router.post("/{case_id}/checklist/ack", response_model=RunOut)
def ack_checklist(case_id: int, session: Session = Depends(get_session)) -> RunOut:
    get_case(session, case_id)
    session.close()
    return run_out(runner.acknowledge_checklist(case_id))


@router.post("/{case_id}/retry", response_model=RunOut)
def retry(case_id: int, session: Session = Depends(get_session)) -> RunOut:
    get_case(session, case_id)
    session.close()
    return run_out(runner.retry(case_id))


@router.get("/{case_id}/timeline", response_model=list[EventOut])
def timeline(case_id: int, session: Session = Depends(get_session)) -> list[EventOut]:
    get_case(session, case_id)
    q = select(Event).where(Event.case_id == case_id).order_by(Event.created_at, Event.id)
    return [EventOut.model_validate(e) for e in session.scalars(q)]


@router.post("/{case_id}/replies", response_model=ReplyOut)
def log_reply(case_id: int, body: ReplyIn, session: Session = Depends(get_session)) -> ReplyOut:
    get_case(session, case_id)
    session.close()
    r = runner.resume_with_reply(case_id, body.text)
    out = ReplyOut(**run_out(r).model_dump())
    with session.begin():
        q = (
            select(Event)
            .where(Event.case_id == case_id, Event.type == "reply_judged")
            .order_by(Event.id.desc())
        )
        ev = session.scalars(q).first()
        if ev is not None:
            out.verdict, out.reason = ev.payload.get("verdict"), ev.payload.get("reason")
    return out


@router.get("/{case_id}/export.pdf")
def export_pdf(case_id: int, session: Session = Depends(get_session)) -> Response:
    from escalate.export.case_pdf import build_case_pdf

    case = get_case(session, case_id)
    pdf = build_case_pdf(session, case)
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="escalate-case-{case_id}.pdf"'},
    )


@router.post("/{case_id}/withdraw", response_model=CaseOut)
def withdraw(case_id: int, body: WithdrawIn, session: Session = Depends(get_session)) -> CaseOut:
    case = get_case(session, case_id)
    if case.status in (CaseStatus.RESOLVED, CaseStatus.WITHDRAWN):
        raise HTTPException(409, f"case is already {case.status}")
    session.close()
    runner.withdraw(case_id, body.reason)
    return CaseOut.model_validate(get_case(session, case_id))
