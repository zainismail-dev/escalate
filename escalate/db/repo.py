"""The scoped repository: the only way routes find cases, messages and their rows.

Local mode (one user, no login): every row is the user's. Hosted mode: every lookup is filtered
on the current user (escalate/db/tenancy.py) and another user's id is indistinguishable from an
id that doesn't exist (the API answers 404, never 403). Without a current user, hosted lookups
fail closed.
"""

from typing import Any

from sqlalchemy import ColumnElement, Select, select, true
from sqlalchemy.orm import Session

from escalate.config import get_settings
from escalate.db.models import Case, Event, Message, Owned
from escalate.db.tenancy import current_user_id


class NoCurrentUser(RuntimeError):
    """Hosted mode reached a scoped lookup without a signed-in user (a bug: fail closed)."""


def _user() -> str | None:
    if not get_settings().hosted:
        return None
    uid = current_user_id()
    if uid is None:
        raise NoCurrentUser("hosted mode: no current user")
    return uid


def mine(model: type[Owned]) -> ColumnElement[bool]:
    uid = _user()
    return true() if uid is None else model.user_id == uid


def owned(row: Owned | None) -> bool:
    uid = _user()
    return row is not None and (uid is None or row.user_id == uid)


def case_pk(session: Session, public_id: str) -> int | None:
    return session.scalar(select(Case.id).where(Case.public_id == public_id, mine(Case)))


def message_pk(session: Session, public_id: str) -> int | None:
    return session.scalar(select(Message.id).where(Message.public_id == public_id, mine(Message)))


def get_case(session: Session, pk: int) -> Case | None:
    case = session.get(Case, pk)
    return case if owned(case) else None


def get_message(session: Session, pk: int) -> Message | None:
    msg = session.get(Message, pk)
    return msg if owned(msg) else None


def cases() -> Select[Case]:
    return select(Case).where(mine(Case))


def case_ids(session: Session) -> list[int]:
    return list(session.scalars(select(Case.id).where(mine(Case))))


def events(session: Session, case_id: int, type: str | None = None) -> list[Event]:
    q = select(Event).where(Event.case_id == case_id, mine(Event))
    if type is not None:
        return list(session.scalars(q.where(Event.type == type).order_by(Event.id.desc())))
    return list(session.scalars(q.order_by(Event.created_at, Event.id)))


def case_message(session: Session, case_id: int, message_id: Any) -> Message | None:
    """A message of this case (ids from the case's own agent state)."""
    msg = session.get(Message, message_id)
    return msg if owned(msg) and msg is not None and msg.case_id == case_id else None


OPEN_STATUSES_EXCLUDED = ("resolved", "withdrawn", "closed_unresolved")


def open_case_count(session: Session) -> int:
    return len(
        session.scalars(
            select(Case.id).where(mine(Case), Case.status.not_in(OPEN_STATUSES_EXCLUDED))
        ).all()
    )
