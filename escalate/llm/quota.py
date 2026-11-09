"""Hosted mode: AI use per user per day and for everyone together. Reserved in the database before
each call, so restarts and several API processes agree and parallel calls can't overshoot.

- Calls (AI_CALLS_PER_DAY, GLOBAL_AI_CALLS_PER_DAY): only successful completions stay counted.
  A refused call is not counted; a failed one (error, 4xx/5xx, timeout) is given back.
- Tokens (AI_TOKENS_PER_DAY, GLOBAL_AI_TOKENS_PER_DAY), estimated from the prompt's size: they
  were sent, so they stay counted when the call fails.
- Failures (AI_FAILURES_PER_DAY): a user whose calls keep failing stops calling the provider
  until tomorrow.
"""

import math
from datetime import date

from sqlalchemy import Insert, select, update
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from escalate.config import Settings, get_settings
from escalate.db.models import GLOBAL_USAGE, AiUsage, utcnow
from escalate.db.session import session_scope
from escalate.db.tenancy import current_user_id
from escalate.llm.client import LLM, Slot


class AiQuotaError(Exception):
    """A friendly refusal: nothing was sent to the AI."""


class AiBusy(AiQuotaError):
    """The beta's daily AI budget (all users) is used up."""


class AiDailyLimit(AiQuotaError):
    """This user's daily AI calls (or tokens) are used up."""


class AiFailureLimit(AiQuotaError):
    """This user's AI calls failed too often today."""


CHARS_PER_TOKEN = 4  # a rough, provider-neutral estimate
OUTPUT_TOKENS = 1024  # what one answer may add


def estimate_tokens(prompt: str) -> int:
    return math.ceil(len(prompt) / CHARS_PER_TOKEN) + OUTPUT_TOKENS


def _upsert(session: Session, user_id: str, day: date, tokens: int) -> tuple[int, int]:
    """Add one call and its tokens; return the new (calls, tokens) (one atomic statement)."""
    dialect = session.get_bind().dialect.name
    ins = postgresql.insert(AiUsage) if dialect == "postgresql" else sqlite.insert(AiUsage)
    stmt: Insert = ins.values(user_id=user_id, day=day, calls=1, tokens=tokens, failures=0)
    stmt = stmt.on_conflict_do_update(  # type: ignore[attr-defined]
        index_elements=[AiUsage.user_id, AiUsage.day],
        set_={"calls": AiUsage.calls + 1, "tokens": AiUsage.tokens + tokens},
    ).returning(AiUsage.calls, AiUsage.tokens)
    calls, used = session.execute(stmt).one()
    return int(calls), int(used)


def failures_today(session: Session, user_id: str, day: date) -> int:
    n = session.scalar(
        select(AiUsage.failures).where(AiUsage.user_id == user_id, AiUsage.day == day)
    )
    return int(n or 0)


def charge(user_id: str | None, tokens: int = 0, settings: Settings | None = None) -> date:
    """Count one AI call of about `tokens` and return the day it counts on, or raise (and count
    nothing) when a limit is reached."""
    s = settings or get_settings()
    day = utcnow().date()
    with session_scope() as session:  # rolled back when a limit is hit
        if user_id is not None and failures_today(session, user_id, day) >= s.ai_failures_per_day:
            raise AiFailureLimit(
                "The AI failed too many times for you today, so it's paused until tomorrow."
            )
        calls, used = _upsert(session, GLOBAL_USAGE, day, tokens)
        if calls > s.global_ai_calls_per_day or used > s.global_ai_tokens_per_day:
            raise AiBusy("The AI is busy today, try tomorrow.")
        if user_id is not None:
            calls, used = _upsert(session, user_id, day, tokens)
            if calls > s.ai_calls_per_day or used > s.ai_tokens_per_day:
                raise AiDailyLimit("You've used today's AI allowance. Try again tomorrow.")
    return day


def refund(user_id: str | None, day: date) -> None:
    """A charged call failed: give the call back (on the day it was charged, even past midnight)
    and count the failure. Its tokens were sent, so they stay counted."""
    owners = [GLOBAL_USAGE, *([user_id] if user_id is not None else [])]
    with session_scope() as session:
        session.execute(
            update(AiUsage)
            .where(AiUsage.user_id.in_(owners), AiUsage.day == day, AiUsage.calls > 0)
            .values(calls=AiUsage.calls - 1, failures=AiUsage.failures + 1)
        )


def calls_today(session: Session, user_id: str) -> int:
    row = session.get(AiUsage, (user_id, utcnow().date()))
    return row.calls if row else 0


class MeteredLLM:
    """Wraps the model: every call is charged to the current user first, and given back if it
    fails."""

    def __init__(self, inner: LLM) -> None:
        self.inner = inner

    def complete(self, prompt: str, slot: Slot = "smart", json_mode: bool = False) -> str:
        user_id = current_user_id()
        day = charge(user_id, estimate_tokens(prompt))
        try:
            return self.inner.complete(prompt, slot=slot, json_mode=json_mode)
        except Exception:
            refund(user_id, day)
            raise
