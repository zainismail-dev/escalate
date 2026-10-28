"""Case endpoints."""

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from escalate.agent import runner
from escalate.agent.deadlines import deadline_status
from escalate.api import views
from escalate.api.deps import get_case, get_session
from escalate.api.schemas import (
    AnswersIn,
    CaseCreate,
    CaseDetail,
    CaseOut,
    CaseSummary,
    DeadlineOut,
    EventOut,
    EvidenceOut,
    LadderStepOut,
    LanguageIn,
    MessageOut,
    ReasonOut,
    ReplyIn,
    ReplyOut,
    RunOut,
    SourceOut,
    WithdrawIn,
)
from escalate.config import get_settings
from escalate.db.events import log_event
from escalate.db.models import Case, CaseStatus, Event, Message
from escalate.evidence.store import save_upload
from escalate.i18n.countries import currency_for, is_rtl
from escalate.pii import mask_pii
from escalate.playbooks.loader import PlaybookError, get_playbook
from escalate.playbooks.models import Playbook
from escalate.safety import new_case_limiter, require_evidence

router = APIRouter(prefix="/cases", tags=["cases"])


def run_out(r: runner.RunResult) -> RunOut:
    return RunOut(
        case_id=r.case_id, waiting_for=r.waiting_for, pending=r.pending, warnings=r.warnings or []
    )


def _playbook(case: Case) -> Playbook | None:
    if not case.playbook_id:
        return None
    try:
        return get_playbook(case.playbook_id)
    except PlaybookError:
        return None


def case_summary(case: Case) -> CaseSummary:
    out = CaseSummary.model_validate(case)
    pending = runner.pending(case.id)
    out.waiting_for = pending.get("type") if pending else None
    pb = _playbook(case)
    if pb is not None:
        out.generic_playbook = pb.generic
        out.ladder = [LadderStepOut(**r) for r in views.ladder(pb, case)]
        out.deadline_warning = any(d.warn or d.late for d in deadline_status(case, pb))
        if case.current_step:
            out.step_name = pb.step(case.current_step).title
    return out


def case_detail(session: Session, case: Case) -> CaseDetail:
    session.refresh(case)
    detail = CaseDetail.model_validate(case)
    detail.pending = runner.pending(case.id)
    detail.waiting_for = detail.pending.get("type") if detail.pending else None
    detail.text_direction = "rtl" if is_rtl(case.language) else "ltr"
    if detail.pending and detail.pending.get("type") == "approve_draft":
        msg = session.get(Message, detail.pending["draft"]["message_id"])
        detail.pending_draft = MessageOut.model_validate(msg) if msg else None
    pb = _playbook(case)
    if pb is not None:
        detail.generic_playbook = pb.generic
        detail.deadlines = [DeadlineOut(**vars(d)) for d in deadline_status(case, pb)]
        detail.ladder = [LadderStepOut(**r) for r in views.ladder(pb, case)]
        detail.reasons = [ReasonOut(**r) for r in views.reasons(pb, case)]
        detail.sources = [SourceOut(title=x.title, url=x.url) for x in pb.sources]
        if case.current_step:
            detail.step_name = pb.step(case.current_step).title
    return detail


@router.post("", response_model=CaseDetail, status_code=201)
def create_case(
    body: CaseCreate, request: Request, session: Session = Depends(get_session)
) -> CaseDetail:
    settings = get_settings()
    client = request.client.host if request.client else "local"
    new_case_limiter.check(client, settings.max_new_cases_per_hour)
    country = body.country or settings.default_country
    case = Case(
        description=mask_pii(body.description.strip()),
        country=country,
        region=body.region,
        language=body.language or settings.default_language,
        company=body.company,
        currency=currency_for(country),
    )
    if case.region and case.country and not case.region.startswith(case.country + "-"):
        raise HTTPException(422, f"region {case.region} is not in country {case.country}")
    session.add(case)
    session.flush()
    log_event(session, case.id, "case_created", {"country": case.country, "region": case.region})
    session.commit()
    return case_detail(session, case)


@router.get("", response_model=list[CaseSummary])
def list_cases(
    status: str | None = None,
    country: str | None = None,
    q: str | None = None,
    session: Session = Depends(get_session),
) -> list[CaseSummary]:
    query = select(Case).order_by(Case.id.desc())
    if status:
        query = query.where(Case.status == status)
    if country:
        query = query.where(Case.country == country.strip().upper())
    if q and q.strip():
        like = f"%{q.strip()}%"
        query = query.where(Case.description.ilike(like) | Case.company.ilike(like))
    return [case_summary(c) for c in session.scalars(query)]


@router.get("/{case_id}", response_model=CaseDetail)
def read_case(case_id: int, session: Session = Depends(get_session)) -> CaseDetail:
    return case_detail(session, get_case(session, case_id))


@router.post("/{case_id}/evidence", response_model=EvidenceOut, status_code=201)
async def upload_evidence(
    case_id: int, file: UploadFile = File(...), session: Session = Depends(get_session)
) -> EvidenceOut:
    get_case(session, case_id)
    settings = get_settings()
    limit = settings.upload_limit_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"file is larger than {settings.upload_limit_mb} MB")
    if not data:
        raise HTTPException(422, "empty file")
    ev = save_upload(session, case_id, file.filename or "upload", data)
    session.commit()
    return EvidenceOut.model_validate(ev)


@router.post("/{case_id}/start", response_model=RunOut)
def start(case_id: int, session: Session = Depends(get_session)) -> RunOut:
    require_evidence(get_case(session, case_id))
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


@router.post("/{case_id}/letter-language", response_model=RunOut)
def letter_language(
    case_id: int, body: LanguageIn, session: Session = Depends(get_session)
) -> RunOut:
    """Change the letter language. A draft waiting for approval is redrafted in it (the old draft
    is rejected, never sent)."""
    case = get_case(session, case_id)
    old, case.language = case.language, body.language
    log_event(session, case_id, "letter_language_changed", {"from": old, "to": body.language})
    session.commit()
    session.close()
    p = runner.pending(case_id)
    if p and p.get("type") == "approve_draft":
        reason = f"letter language changed to {body.language}"
        return run_out(runner.resume_with_decision(case_id, "reject", reason=reason))
    return RunOut(case_id=case_id, waiting_for=p.get("type") if p else None, pending=p)


@router.post("/{case_id}/withdraw", response_model=CaseOut)
def withdraw(case_id: int, body: WithdrawIn, session: Session = Depends(get_session)) -> CaseOut:
    case = get_case(session, case_id)
    if case.status in (CaseStatus.RESOLVED, CaseStatus.WITHDRAWN):
        raise HTTPException(409, f"case is already {case.status}")
    session.close()
    runner.withdraw(case_id, body.reason)
    return CaseOut.model_validate(get_case(session, case_id))


@router.delete("/{case_id}", status_code=204)
def delete_case(case_id: int, session: Session = Depends(get_session)) -> Response:
    get_case(session, case_id)
    session.close()
    runner.delete_case(case_id)
    return Response(status_code=204)
