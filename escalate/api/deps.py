"""Shared API dependencies and error mapping."""

from collections.abc import Iterator

from fastapi import HTTPException
from sqlalchemy.orm import Session

from escalate.db.models import Case, Message
from escalate.db.session import session_factory


def get_session() -> Iterator[Session]:
    s = session_factory()()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def get_case(session: Session, case_id: int) -> Case:
    case = session.get(Case, case_id)
    if case is None:
        raise HTTPException(404, f"case {case_id} not found")
    return case


def get_message(session: Session, message_id: int) -> Message:
    msg = session.get(Message, message_id)
    if msg is None:
        raise HTTPException(404, f"message {message_id} not found")
    return msg
