"""Hosted mode: AI calls per user per day (AI_CALLS_PER_DAY) and for everyone together
(GLOBAL_AI_CALLS_PER_DAY). Counted in the database before each call, so restarts and several
API processes agree; a refused call is not counted."""

from datetime import date

from sqlalchemy import Insert
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
    """This user's daily AI calls are used up."""


def _upsert(session: Session, user_id: str, day: date) -> int:
    """Add one call and return the new count (one atomic statement)."""
    dialect = session.get_bind().dialect.name
    ins = postgresql.insert(AiUsage) if dialect == "postgresql" else sqlite.insert(AiUsage)
    stmt: Insert = ins.values(user_id=user_id, day=day, calls=1)
    stmt = stmt.on_conflict_do_update(  # type: ignore[attr-defined]
        index_elements=[AiUsage.user_id, AiUsage.day], set_={"calls": AiUsage.calls + 1}
    ).returning(AiUsage.calls)
    return int(session.execute(stmt).scalar_one())


def charge(user_id: str | None, settings: Settings | None = None) -> None:
    """Count one AI call, or raise (and count nothing) when a limit is reached."""
    s = settings or get_settings()
    day = utcnow().date()
    with session_scope() as session:  # rolled back when a limit is hit
        if _upsert(session, GLOBAL_USAGE, day) > s.global_ai_calls_per_day:
            raise AiBusy("The AI is busy today, try tomorrow.")
        if user_id is not None and _upsert(session, user_id, day) > s.ai_calls_per_day:
            raise AiDailyLimit(
                f"You've used today's {s.ai_calls_per_day} AI requests. Try again tomorrow."
            )


def calls_today(session: Session, user_id: str) -> int:
    row = session.get(AiUsage, (user_id, utcnow().date()))
    return row.calls if row else 0


class MeteredLLM:
    """Wraps the model: every call is charged to the current user first."""

    def __init__(self, inner: LLM) -> None:
        self.inner = inner

    def complete(self, prompt: str, slot: Slot = "smart") -> str:
        charge(current_user_id())
        return self.inner.complete(prompt, slot=slot)
