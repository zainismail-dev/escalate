"""Case endpoints."""

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from escalate.agent import runner
from escalate.agent.deadlines import deadline_status
from escalate.agent.review import display_value
from escalate.agent.titles import display_title
from escalate.api import views
from escalate.api.deps import CasePk, get_case, get_session, public_case_id, public_pending
from escalate.api.schemas import (
    AnswersIn,
    CaseCreate,
    CaseDetail,
    CaseOut,
    CaseSummary,
    CaseUpdate,
    DeadlineOut,
    EventOut,
    EvidenceOut,
    LadderStepOut,
    LanguageIn,
    MessageOut,
    ReasonOut,
    ReplyIn,
    ReplyOut,
    ResolutionIn,
    RunOut,
    SourceOut,
    VerdictIn,
    WithdrawIn,
)
from escalate.config import get_settings
from escalate.db.events import log_event
from escalate.db.models import Case, CaseStatus, Event, Message, utcnow
from escalate.db.session import session_scope
from escalate.evidence.sniff import UploadRejected, check_upload
from escalate.evidence.store import safe_filename, save_upload
from escalate.i18n.countries import currency_for, default_letter_language, is_rtl
from escalate.i18n.formatting import format_amount, locale_for
from escalate.pii import mask_pii
from escalate.playbooks.loader import PlaybookError, get_playbook
from escalate.playbooks.models import Playbook
from escalate.safety import new_case_limiter, require_evidence

router = APIRouter(prefix="/cases", tags=["cases"])


def run_out(r: runner.RunResult) -> RunOut:
    """The agent's state for the API, with public ids only."""
    with session_scope() as s:
        return RunOut(
            case_id=public_case_id(s, r.case_id),
            waiting_for=r.waiting_for,
            pending=public_pending(s, r.pending),
            warnings=r.warnings or [],
        )


def _playbook(case: Case) -> Playbook | None:
    if not case.playbook_id:
        return None
    try:
        return get_playbook(case.playbook_id)
    except PlaybookError:
        return None


def _amount_display(case: Case) -> str | None:
    if case.amount is None:
        return None
    return format_amount(case.amount, case.currency, locale_for(case.language, case.country))


def case_summary(case: Case) -> CaseSummary:
    out = CaseSummary.model_validate(case)
    out.title = display_title(case)
    out.amount_display = _amount_display(case)
    pending = runner.pending(case.id)
    out.waiting_for = pending.get("type") if pending else None
    pb = _playbook(case)
    dues: list[int] = []
    if case.next_action_at is not None:
        dues.append((case.next_action_at.date() - utcnow().date()).days)
    if pb is not None:
        out.generic_playbook = pb.generic
        out.ladder = [LadderStepOut(**r) for r in views.ladder(pb, case)]
        status = deadline_status(case, pb)
        out.deadline_warning = any(d.warn or d.late for d in status)
        dues += [d.days_left for d in status if d.days_left is not None]
        if case.current_step:
            out.step_name = pb.step(case.current_step).title
    open_case = case.status not in (CaseStatus.RESOLVED, CaseStatus.WITHDRAWN)
    out.days_left = min(dues) if dues and open_case else None
    return out


def _list_order(c: CaseSummary) -> tuple[int, int, float]:
    """Urgent (scam checklist) first, then the nearest deadline, then the newest."""
    urgent = 0 if c.waiting_for == "urgent_checklist" else 1
    due = c.days_left if c.days_left is not None else 10**6
    return (urgent, due, -c.created_at.timestamp())


def case_detail(session: Session, case: Case) -> CaseDetail:
    session.refresh(case)
    detail = CaseDetail.model_validate(case)
    detail.title = display_title(case)
    detail.amount_display = _amount_display(case)
    for f in detail.facts:
        f.display = display_value(case, f.key, f.value)
    raw = runner.pending(case.id)
    detail.pending = public_pending(session, raw)
    detail.waiting_for = raw.get("type") if raw else None
    detail.text_direction = "rtl" if is_rtl(case.language) else "ltr"
    if detail.pending and detail.pending.get("type") == "approve_draft":
        msg = session.get(Message, raw["draft"]["message_id"]) if raw else None
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
        language=body.language or default_letter_language(),
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
    status: str | None = Query(default=None, max_length=40),
    country: str | None = Query(default=None, max_length=2),
    q: str | None = Query(default=None, max_length=200),
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
    return sorted((case_summary(c) for c in session.scalars(query)), key=_list_order)


@router.get("/{case_id}", response_model=CaseDetail)
def read_case(case_id: CasePk, session: Session = Depends(get_session)) -> CaseDetail:
    return case_detail(session, get_case(session, case_id))


@router.patch("/{case_id}", response_model=CaseDetail)
def update_case(
    case_id: CasePk, body: CaseUpdate, session: Session = Depends(get_session)
) -> CaseDetail:
    """Rename a case. The agent never overwrites a title once it is set."""
    case = get_case(session, case_id)
    case.title = mask_pii(body.title)
    log_event(session, case_id, "title_set", {"title": case.title, "by": "user"})
    session.commit()
    return case_detail(session, case)


@router.post("/{case_id}/evidence", response_model=EvidenceOut, status_code=201)
async def upload_evidence(
    case_id: CasePk, file: UploadFile = File(...), session: Session = Depends(get_session)
) -> EvidenceOut:
    get_case(session, case_id)
    settings = get_settings()
    limit = settings.upload_limit_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"file is larger than {settings.upload_limit_mb} MB")
    if not data:
        raise HTTPException(422, "empty file")
    name = safe_filename(file.filename or "upload")
    try:
        check_upload(name, data)
    except UploadRejected as exc:
        raise HTTPException(415, str(exc)) from exc
    ev = save_upload(session, case_id, name, data)
    session.commit()
    return EvidenceOut.model_validate(ev)


@router.post("/{case_id}/start", response_model=RunOut)
def start(case_id: CasePk, session: Session = Depends(get_session)) -> RunOut:
    require_evidence(get_case(session, case_id))
    session.close()
    if runner.pending(case_id) is not None:
        raise HTTPException(409, "case already started")
    return run_out(runner.start_case(case_id))


@router.post("/{case_id}/answers", response_model=RunOut)
def answers(case_id: CasePk, body: AnswersIn, session: Session = Depends(get_session)) -> RunOut:
    get_case(session, case_id)
    session.close()
    return run_out(runner.resume_with_answers(case_id, body.answers))


@router.post("/{case_id}/checklist/ack", response_model=RunOut)
def ack_checklist(case_id: CasePk, session: Session = Depends(get_session)) -> RunOut:
    get_case(session, case_id)
    session.close()
    return run_out(runner.acknowledge_checklist(case_id))


@router.post("/{case_id}/retry", response_model=RunOut)
def retry(case_id: CasePk, session: Session = Depends(get_session)) -> RunOut:
    get_case(session, case_id)
    session.close()
    return run_out(runner.retry(case_id))


@router.get("/{case_id}/timeline", response_model=list[EventOut])
def timeline(case_id: CasePk, session: Session = Depends(get_session)) -> list[EventOut]:
    get_case(session, case_id)
    q = select(Event).where(Event.case_id == case_id).order_by(Event.created_at, Event.id)
    return [EventOut.model_validate(e) for e in session.scalars(q)]


@router.post("/{case_id}/replies", response_model=ReplyOut)
def log_reply(case_id: CasePk, body: ReplyIn, session: Session = Depends(get_session)) -> ReplyOut:
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
            p = ev.payload
            out.verdict, out.reason = p.get("verdict"), p.get("reason")
            out.promise, out.promise_date = p.get("promise"), p.get("promise_date")
            out.condition = p.get("condition")
    return out


@router.post("/{case_id}/resolution", response_model=RunOut)
def confirm_resolution(
    case_id: CasePk, body: ResolutionIn, session: Session = Depends(get_session)
) -> RunOut:
    """The user confirms (or denies) that the company's reply resolved the case."""
    get_case(session, case_id)
    session.close()
    return run_out(runner.confirm_resolution(case_id, body.resolved, body.verdict))


@router.post("/{case_id}/verdict", response_model=RunOut)
def override_verdict(
    case_id: CasePk, body: VerdictIn, session: Session = Depends(get_session)
) -> RunOut:
    """The user corrects the agent's verdict on the last reply; the ladder is replayed from it."""
    get_case(session, case_id)
    session.close()
    return run_out(runner.override_verdict(case_id, body.verdict))


@router.get("/{case_id}/export.pdf")
def export_pdf(case_id: CasePk, session: Session = Depends(get_session)) -> Response:
    from escalate.export.case_pdf import build_case_pdf

    case = get_case(session, case_id)
    pdf = build_case_pdf(session, case)
    return Response(
        pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="escalate-case-{case.public_id}.pdf"'
        },
    )


@router.post("/{case_id}/letter-language", response_model=RunOut)
def letter_language(
    case_id: CasePk, body: LanguageIn, session: Session = Depends(get_session)
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
    return run_out(runner.RunResult(case_id, p))


@router.post("/{case_id}/withdraw", response_model=CaseOut)
def withdraw(case_id: CasePk, body: WithdrawIn, session: Session = Depends(get_session)) -> CaseOut:
    case = get_case(session, case_id)
    if case.status in (CaseStatus.RESOLVED, CaseStatus.WITHDRAWN):
        raise HTTPException(409, f"case is already {case.status}")
    session.close()
    runner.withdraw(case_id, body.reason)
    case = get_case(session, case_id)
    out = CaseOut.model_validate(case)
    out.title = display_title(case)
    return out


@router.delete("/{case_id}", status_code=204)
def delete_case(case_id: CasePk, session: Session = Depends(get_session)) -> Response:
    get_case(session, case_id)
    session.close()
    runner.delete_case(case_id)
    return Response(status_code=204)
