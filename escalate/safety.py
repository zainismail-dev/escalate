"""Abuse limits: rate limit new cases, require evidence, and refuse harassment patterns."""

import threading
from collections import deque
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from escalate.config import Settings, get_settings
from escalate.db.models import Case, Message, utcnow


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


def check_recipient(session: Session, msg: Message, settings: Settings | None = None) -> None:
    """Refuse when the same recipient already gets letters from too many other cases."""
    s = settings or get_settings()
    if not msg.recipient:
        return
    since = utcnow() - timedelta(days=s.recipient_window_days)
    others = session.scalar(
        select(func.count(func.distinct(Message.case_id))).where(
            func.lower(Message.recipient) == msg.recipient.strip().lower(),
            Message.case_id != msg.case_id,
            Message.direction == "out",
            Message.approved_at.is_not(None),
            Message.approved_at >= since,
        )
    )
    if (others or 0) + 1 > s.max_cases_per_recipient:
        raise HarassmentPattern(
            f"{msg.recipient} already receives letters from {others} other cases in the last "
            f"{s.recipient_window_days} days; Escalate refuses repeated campaigns against one "
            "recipient"
        )
