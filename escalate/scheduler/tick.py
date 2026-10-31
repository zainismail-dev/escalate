"""Hosted mode has no in-process scheduler (the free API sleeps when idle). An hourly external
cron calls POST /internal/tick, which runs every due wake-up and the deadline scan.

Idempotent: a wake-up only resumes a case still waiting for that step's reply, and deadline
warnings are logged once per deadline per day. Each case runs as its owner, so its AI calls
count against that user's quota and nothing crosses users.
"""

import logging
from dataclasses import asdict, dataclass

from sqlalchemy import select

from escalate.agent import runner
from escalate.config import get_settings
from escalate.db.models import Case, CaseStatus, utcnow
from escalate.db.session import session_scope
from escalate.db.tenancy import as_user
from escalate.llm.quota import AiQuotaError, calls_today
from escalate.scheduler.jobs import scan_deadlines

log = logging.getLogger("uvicorn.error")
AI_HEADROOM = 5  # AI calls a wake-up may need (reply judging, next draft, fact check)


@dataclass
class TickResult:
    woke: int = 0
    skipped: int = 0
    failed: int = 0
    deadline_warnings: int = 0


def due_cases() -> list[tuple[int, str | None]]:
    with session_scope() as s:
        rows = s.execute(
            select(Case.id, Case.user_id).where(
                Case.status == CaseStatus.WAITING_REPLY,
                Case.next_action_at.is_not(None),
                Case.next_action_at <= utcnow(),
            )
        )
        return [(cid, uid) for cid, uid in rows]


def _has_ai_room(user_id: str | None) -> bool:
    from escalate.db.models import GLOBAL_USAGE

    s = get_settings()
    with session_scope() as session:
        if calls_today(session, GLOBAL_USAGE) + AI_HEADROOM > s.global_ai_calls_per_day:
            return False
        return user_id is None or calls_today(session, user_id) + AI_HEADROOM <= s.ai_calls_per_day


def run_tick() -> dict[str, int]:
    result = TickResult()
    for case_id, owner in due_cases():
        with as_user(owner):
            pending = runner.pending(case_id)
            if not pending or pending.get("type") != "waiting_reply":
                result.skipped += 1
                continue
            if not _has_ai_room(owner):  # try again next hour rather than stop half-way
                result.skipped += 1
                continue
            try:
                woke = runner.resume_timeout(case_id, str(pending.get("step")))
            except AiQuotaError:
                result.skipped += 1
                continue
            except Exception as exc:  # one broken case must not stop the others
                log.error("tick: case wake-up failed: %s", type(exc).__name__, exc_info=exc)
                result.failed += 1
                continue
            if woke is None:
                result.skipped += 1
            else:
                result.woke += 1
    result.deadline_warnings = scan_deadlines()
    return asdict(result)
