"""Abuse limits: rate limit new cases, require evidence, and refuse harassment patterns."""

import hashlib
import hmac
import threading
from collections import deque
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from escalate.config import Settings, get_settings
from escalate.db.models import Case, Message, RecipientContact, utcnow


class SafetyError(Exception):
    """A request was refused to prevent abuse."""


class RateLimited(SafetyError):
    pass


class NoEvidence(SafetyError):
    pass


class HarassmentPattern(SafetyError):
    pass


class RateLimiter:
    """Sliding one-hour window per key (e.g. client IP). In memory: one API process."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(
        self,
        key: str,
        limit: int,
        window: timedelta = timedelta(hours=1),
        what: str = "new cases",
    ) -> None:
        now = utcnow().timestamp()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= now - window.total_seconds():
                hits.popleft()
            if len(hits) >= limit:
                per = "hour" if window == timedelta(hours=1) else f"{int(window.total_seconds())} s"
                raise RateLimited(f"too many {what}; try again later (limit {limit} per {per})")
            hits.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


new_case_limiter = RateLimiter()


def require_evidence(case: Case, settings: Settings | None = None) -> None:
    s = settings or get_settings()
    if s.require_evidence and not case.evidence:
        raise NoEvidence(
            "upload at least one piece of evidence (receipt, screenshot, email) before starting"
        )


GMAIL = {"gmail.com", "googlemail.com"}


def normalise_recipient(recipient: str) -> str:
    """One mailbox, one key: lowercase, no "+tag", and Gmail ignores dots (and googlemail.com
    is gmail.com). Anything else (a postal address) is lowercased with spaces collapsed."""
    value = " ".join(recipient.split()).lower()
    local, at, domain = value.rpartition("@")
    if not at or not local or " " in value:
        return value
    local = local.split("+", 1)[0]
    if domain in GMAIL:
        local, domain = local.replace(".", ""), "gmail.com"
    return f"{local}@{domain}"


def _hash(value: str, settings: Settings) -> str:
    key = (settings.fernet_key or "escalate-recipient-contacts").encode()
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()


def recipient_hash(recipient: str, settings: Settings | None = None) -> str:
    return _hash("recipient:" + normalise_recipient(recipient), settings or get_settings())


def case_hash(case: Case, settings: Settings | None = None) -> str:
    return _hash("case:" + case.public_id, settings or get_settings())


def record_recipient(session: Session, msg: Message, settings: Settings | None = None) -> None:
    """After an approval: remember (as hashes only) that this case wrote to this recipient."""
    if not msg.recipient:
        return
    s = settings or get_settings()
    session.add(
        RecipientContact(
            recipient_hash=recipient_hash(msg.recipient, s),
            case_hash=case_hash(msg.case, s),
            contacted_at=msg.approved_at or utcnow(),
        )
    )


def check_recipient(session: Session, msg: Message, settings: Settings | None = None) -> None:
    """Refuse when the same recipient already gets letters from too many other cases. Counts
    the hashed records (which survive case deletion) and live approved messages, with
    recipients normalised (case, +tags, Gmail dots)."""
    s = settings or get_settings()
    if not msg.recipient:
        return
    since = utcnow() - timedelta(days=s.recipient_window_days)
    target = recipient_hash(msg.recipient, s)
    mine = case_hash(msg.case, s)
    cases = set(
        session.scalars(
            select(RecipientContact.case_hash).where(
                RecipientContact.recipient_hash == target,
                RecipientContact.contacted_at >= since,
            )
        )
    )
    live = session.execute(
        select(Message.recipient, Case.public_id)
        .join(Case, Message.case_id == Case.id)
        .where(
            Message.case_id != msg.case_id,
            Message.direction == "out",
            Message.approved_at.is_not(None),
            Message.approved_at >= since,
            Message.recipient.is_not(None),
        )
    )
    for recipient, public_id in live:
        if recipient and recipient_hash(recipient, s) == target:
            cases.add(_hash("case:" + public_id, s))
    cases.discard(mine)
    others = len(cases)
    if others + 1 > s.max_cases_per_recipient:
        raise HarassmentPattern(
            f"{msg.recipient} already receives letters from {others} other cases in the last "
            f"{s.recipient_window_days} days; Escalate refuses repeated campaigns against one "
            "recipient"
        )
