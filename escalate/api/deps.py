"""Shared API dependencies and error mapping."""

from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import Depends, HTTPException
from sqlalchemy import select
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


# The API only accepts unguessable public ids (UUIDs) in paths; routes get the internal id.
def case_pk(case_id: str, session: Session = Depends(get_session)) -> int:
    pk = session.scalar(select(Case.id).where(Case.public_id == case_id))
    if pk is None:
        raise HTTPException(404, "case not found")
    return pk


def message_pk(message_id: str, session: Session = Depends(get_session)) -> int:
    pk = session.scalar(select(Message.id).where(Message.public_id == message_id))
    if pk is None:
        raise HTTPException(404, "message not found")
    return pk


CasePk = Annotated[int, Depends(case_pk)]
MessagePk = Annotated[int, Depends(message_pk)]


def public_case_id(session: Session, pk: int) -> str:
    return session.scalar(select(Case.public_id).where(Case.id == pk)) or ""


def public_pending(session: Session, pending: dict[str, Any] | None) -> dict[str, Any] | None:
    """Interrupt payloads carry internal message ids; the API shows public ones."""
    if not pending:
        return pending
    out = dict(pending)

    def pub(mid: object) -> str | None:
        return session.scalar(select(Message.public_id).where(Message.id == mid))

    if isinstance(out.get("draft"), dict) and "message_id" in out["draft"]:
        out["draft"] = {**out["draft"], "message_id": pub(out["draft"]["message_id"])}
    if "message_id" in out:
        out["message_id"] = pub(out["message_id"])
    return out
