"""Hosted accounts: the user row, invites, consent and per-user settings."""

import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from escalate.config import get_settings
from escalate.db import repo
from escalate.db.models import Invite, User, UserSettings, utcnow
from escalate.hosted.jwt import Identity

EMAIL_RE = re.compile(r"[^@\s]{1,64}@[^@\s]{1,255}")


class Waitlisted(Exception):
    """Signed in, but not invited to the beta."""


class ConsentRequired(Exception):
    """Invited, but the first-run consent has not been given yet."""


class OpenCaseLimit(Exception):
    """Hosted beta: MAX_OPEN_CASES per user."""


_case_count_locks: dict[str, threading.Lock] = {}
_case_count_guard = threading.Lock()


@contextmanager
def case_count_lock(user_id: str | None) -> Iterator[None]:
    """Hold around "check the open-case limit, open a case, commit", so two parallel requests
    can't both take the last slot. Per process here; check_open_case_slot also locks the user's
    row, which holds across processes on Postgres. Local mode (no user): nothing to lock."""
    if user_id is None:
        yield
        return
    with _case_count_guard:
        lock = _case_count_locks.setdefault(user_id, threading.Lock())
    with lock:
        yield


def check_open_case_slot(session: Session, user_id: str | None) -> None:
    """Raise OpenCaseLimit when opening (or reopening) one more case would pass MAX_OPEN_CASES.
    Call inside case_count_lock, and commit before leaving it."""
    s = get_settings()
    if not s.hosted or user_id is None:
        return
    session.execute(select(User.id).where(User.id == user_id).with_for_update())
    if repo.open_case_count(session) >= s.max_open_cases:
        raise OpenCaseLimit(
            f"the beta allows {s.max_open_cases} open cases at a time: resolve, withdraw or "
            "delete one first"
        )


def normalise_email(email: str) -> str:
    value = email.strip().lower()
    if len(value) > 320 or not EMAIL_RE.fullmatch(value):
        raise ValueError(f"not an email address: {email!r}")
    return value


def ensure_user(session: Session, identity: Identity) -> User:
    """The user's row, created on their first request (the email follows their Google one)."""
    user = session.get(User, identity.user_id)
    if user is None:
        try:
            with session.begin_nested():
                user = User(id=identity.user_id, email=identity.email)
                session.add(user)
        except IntegrityError:  # a parallel first request created it
            user = session.get(User, identity.user_id)
            assert user is not None
    elif user.email != identity.email:
        user.email = identity.email
    return user


def is_invited(session: Session, email: str) -> bool:
    return session.get(Invite, email.strip().lower()) is not None


def may_join(session: Session, identity: Identity) -> bool:
    """Invited, and the email really is theirs (hosted/jwt.py, `email_trusted`)."""
    return identity.email_trusted and is_invited(session, identity.email)


def require_member(session: Session, identity: Identity) -> User:
    """Raise Waitlisted or ConsentRequired unless this user may use the case routes. Nothing is
    stored about people on the waitlist (their user row is created once they are invited)."""
    if not may_join(session, identity):
        raise Waitlisted("You're on the waitlist")
    user = ensure_user(session, identity)
    if user.consented_at is None:
        raise ConsentRequired("Please read and accept the beta terms first")
    return user


def record_consent(session: Session, identity: Identity) -> User:
    if not may_join(session, identity):
        raise Waitlisted("You're on the waitlist")
    user = ensure_user(session, identity)
    user.consented_at = user.consented_at or utcnow()
    return user


def invite(session: Session, email: str) -> bool:
    """True when the email is newly invited."""
    value = normalise_email(email)
    if session.get(Invite, value) is not None:
        return False
    session.add(Invite(email=value))
    return True


def uninvite(session: Session, email: str) -> bool:
    row = session.get(Invite, normalise_email(email))
    if row is None:
        return False
    session.delete(row)
    return True


def user_settings(session: Session, user_id: str) -> UserSettings:
    row = session.scalar(select(UserSettings).where(UserSettings.user_id == user_id))
    if row is None:
        row = UserSettings(user_id=user_id)
        session.add(row)
        session.flush()
    return row
