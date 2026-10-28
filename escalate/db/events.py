"""Append-only case event log."""

from typing import Any

from sqlalchemy.orm import Session

from escalate.db.models import Case, Event
from escalate.pii import mask_obj


def log_event(
    session: Session, case_id: int, type: str, payload: dict[str, Any] | None = None
) -> Event:
    ev = Event(case_id=case_id, type=type, payload=mask_obj(payload or {}))
    case = session.get(Case, case_id)
    if case is not None:
        case.events.append(ev)  # keeps an already-loaded case.events list current
    session.add(ev)
    session.flush()
    return ev
