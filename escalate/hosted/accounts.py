"""Hosted accounts: the user row, invites, consent and per-user settings."""

import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from escalate.db.models import Invite, User, UserSettings, utcnow
from escalate.hosted.jwt import Identity

EMAIL_RE = re.compile(r"[^@\s]{1,64}@[^@\s]{1,255}")


class Waitlisted(Exception):
    """Signed in, but not invited to the beta."""


class ConsentRequired(Exception):
    """Invited, but the first-run consent has not been given yet."""


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


def require_member(session: Session, identity: Identity) -> User:
    """Raise Waitlisted or ConsentRequired unless this user may use the case routes. Nothing is
    stored about people on the waitlist (their user row is created once they are invited)."""
    if not is_invited(session, identity.email):
        raise Waitlisted("You're on the waitlist")
    user = ensure_user(session, identity)
    if user.consented_at is None:
        raise ConsentRequired("Please read and accept the beta terms first")
    return user


def record_consent(session: Session, identity: Identity) -> User:
    if not is_invited(session, identity.email):
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
