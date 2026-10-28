"""Append-only case event log."""

from typing import Any

from sqlalchemy.orm import Session

from escalate.db.models import Event


def log_event(
    session: Session, case_id: int, type: str, payload: dict[str, Any] | None = None
) -> Event:
    ev = Event(case_id=case_id, type=type, payload=payload or {})
    session.add(ev)
    session.flush()
    return ev
