"""Hosted users' rights: export everything, or delete everything (rows, evidence objects,
agent checkpoints and the Supabase sign-in)."""

import json
import logging
import tempfile
import zipfile
from datetime import date, datetime
from decimal import Decimal
from typing import IO, Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from escalate.agent import runner
from escalate.db import repo
from escalate.db.models import (
    AiUsage,
    Base,
    Case,
    CaseFact,
    Event,
    Evidence,
    Invite,
    Message,
    RecipientContact,
    User,
    UserSettings,
    utcnow,
)
from escalate.db.session import session_scope
from escalate.evidence.store import get_storage, load_plain, safe_filename
from escalate.hosted.jwt import Identity
from escalate.hosted.supabase_admin import get_admin

log = logging.getLogger("uvicorn.error")

# Never exported: internal keys, storage locations and the owner id itself.
HIDDEN = {"id", "case_id", "user_id", "file_path", "source_evidence_id"}


def _row(obj: Base) -> dict[str, Any]:
    return {c.key: getattr(obj, c.key) for c in obj.__table__.columns if c.key not in HIDDEN}


def _json(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(type(value).__name__)


def export_data(session: Session, identity: Identity) -> IO[bytes]:
    """A zip: data.json (account, settings, every case with facts, messages, timeline and
    evidence details), each case's PDF, and the original evidence files."""
    from escalate.export.case_pdf import build_case_pdf
    from escalate.export.pdf import PdfUnavailable

    user = session.get(User, identity.user_id)
    prefs = session.scalar(select(UserSettings).where(UserSettings.user_id == identity.user_id))
    out: IO[bytes] = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)  # noqa: SIM115
    data: dict[str, Any] = {
        "exported_at": utcnow().isoformat(),
        "account": {"email": identity.email, **(_row(user) if user else {})},
        "settings": _row(prefs) if prefs else {},
        "cases": [],
        "notes": [],
    }
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for case in session.scalars(repo.cases().order_by(Case.id)):
            data["cases"].append(_case_data(case))
            try:
                zf.writestr(f"cases/{case.public_id}.pdf", build_case_pdf(session, case))
            except PdfUnavailable:
                data["notes"].append(f"case {case.public_id}: PDF rendering unavailable")
            for n, ev in enumerate(case.evidence, 1):
                name = f"evidence/{case.public_id}/{n}-{safe_filename(ev.filename)}"
                try:
                    zf.writestr(name, load_plain(ev))
                except Exception:  # a missing object must not stop the rest of the export
                    data["notes"].append(f"{name}: could not be read")
        zf.writestr("data.json", json.dumps(data, default=_json, indent=2, ensure_ascii=False))
    out.seek(0)
    return out


def _case_data(case: Case) -> dict[str, Any]:
    return {
        **_row(case),
        "facts": [_row(f) for f in case.facts],
        "messages": [_row(m) for m in case.messages],
        "timeline": [_row(e) for e in case.events],
        "evidence": [_row(e) for e in case.evidence],
    }


OWNED_ROWS = (RecipientContact, UserSettings, Event, Message, CaseFact, Evidence, Case)


def delete_account(identity: Identity) -> None:
    """Everything of this user, then their Supabase sign-in. Safe to run again after a
    failure: each step skips what is already gone."""
    uid = identity.user_id
    with session_scope() as s:
        case_ids = repo.case_ids(s)
    for cid in case_ids:
        runner.delete_case(cid)  # agent checkpoint, evidence objects, rows
    with session_scope() as s:
        for model in OWNED_ROWS:  # anything a crash left behind
            s.execute(delete(model).where(model.user_id == uid))
        s.execute(delete(AiUsage).where(AiUsage.user_id == uid))
        s.execute(delete(Invite).where(Invite.email == identity.email))
        s.execute(delete(User).where(User.id == uid))
    get_storage().delete_user(uid)  # objects an interrupted upload left behind
    get_admin().delete_user(uid)
    log.info("deleted an account and %d case(s)", len(case_ids))
