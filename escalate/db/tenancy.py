"""Hosted mode: every user-owned row carries `user_id`, and no query crosses users.

Two walls, so one forgotten filter can't leak another user's case:

1. Routes resolve ids through the scoped repository (escalate/db/repo.py), which filters on the
   current user and answers 404 for anyone else's id.
2. While a user is current (`as_user`, set by the auth middleware for each request and by the
   tick for each case), every ORM SELECT, UPDATE and DELETE on an owned table gets
   `user_id = <current user>` added (SQLAlchemy's with_loader_criteria), relationship loads
   included.

New rows are stamped here too: a case's facts, evidence, messages and events get the case's
owner when they are flushed, so no code path can create an unowned child row. Local mode never
sets a current user, so none of this changes anything there.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria

from escalate.db.models import (
    Case,
    CaseFact,
    Event,
    Evidence,
    Message,
    Owned,
    RecipientContact,
    UserSettings,
)

OWNED: tuple[type[Owned], ...] = (
    Case,
    CaseFact,
    Evidence,
    Message,
    Event,
    RecipientContact,
    UserSettings,
)
CASE_CHILDREN = (CaseFact, Evidence, Message, Event)

_current_user: ContextVar[str | None] = ContextVar("escalate_current_user", default=None)


def current_user_id() -> str | None:
    return _current_user.get()


@contextmanager
def as_user(user_id: str | None) -> Iterator[None]:
    """Run as `user_id` (None: no user, i.e. local mode or the tick's own bookkeeping)."""
    token = _current_user.set(user_id)
    try:
        yield
    finally:
        _current_user.reset(token)


def set_current_user(user_id: str | None) -> None:
    """For the auth middleware: the request's context (and the threads it starts) only."""
    _current_user.set(user_id)


@event.listens_for(Session, "do_orm_execute")
def _only_current_users_rows(state: ORMExecuteState) -> None:
    uid = _current_user.get()
    if uid is None or not (state.is_select or state.is_update or state.is_delete):
        return
    for model in OWNED:
        state.statement = state.statement.options(
            with_loader_criteria(model, lambda cls: cls.user_id == uid, include_aliases=True)
        )


@event.listens_for(Session, "before_flush")
def _stamp_owner(session: Session, _ctx: Any, _instances: Any) -> None:
    uid = _current_user.get()
    with session.no_autoflush:
        for obj in session.new:
            if isinstance(obj, Case | UserSettings | RecipientContact) and obj.user_id is None:
                obj.user_id = uid
            elif isinstance(obj, CASE_CHILDREN) and obj.user_id is None:
                case = obj.case or (session.get(Case, obj.case_id) if obj.case_id else None)
                obj.user_id = case.user_id if case is not None else uid
