"""Wake-ups and daily deadline scans, persisted in the SQLAlchemy job store (survives restarts).

Job ids are `case-<id>-step-<step>`; re-adding replaces, so there are never duplicates.
"""

import importlib
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.base import BaseScheduler
from sqlalchemy import select
from sqlalchemy.orm import Session

from escalate.config import get_settings
from escalate.db.events import log_event
from escalate.db.models import Case, CaseStatus, Event, utcnow
from escalate.db.session import session_scope

ACTIVE = (CaseStatus.WAITING_REPLY, CaseStatus.AWAITING_APPROVAL, CaseStatus.DRAFTING)
DEADLINE_SCAN_ID = "deadline-scan"

# The runner installs the real handler; kept indirect so this module has no agent imports.
WakeHandler = Callable[[int, str], None]
_wake_handler: WakeHandler | None = None


def set_wake_handler(fn: WakeHandler | None) -> None:
    global _wake_handler
    _wake_handler = fn


def wake_case(case_id: int, step_id: str) -> None:
    """Job target: the wait for `step_id` ran out with no reply."""
    if _wake_handler is None:
        runner = importlib.import_module("escalate.agent.runner")  # avoids an import cycle
        runner.resume_timeout(case_id, step_id)
    else:
        _wake_handler(case_id, step_id)


def job_id(case_id: int, step_id: str) -> str:
    return f"case-{case_id}-step-{step_id}"


def scheduler_config(url: str | None = None) -> dict[str, Any]:
    return {
        "jobstores": {"default": SQLAlchemyJobStore(url=url or get_settings().database_url)},
        "job_defaults": {"coalesce": True, "misfire_grace_time": None, "max_instances": 1},
        "timezone": "UTC",
    }


def make_scheduler(url: str | None = None) -> BackgroundScheduler:
    return BackgroundScheduler(**scheduler_config(url))


def schedule_wake(scheduler: BaseScheduler, case_id: int, step_id: str, when: datetime) -> str:
    jid = job_id(case_id, step_id)
    scheduler.add_job(
        "escalate.scheduler.jobs:wake_case",
        trigger="date",
        run_date=when,
        args=[case_id, step_id],
        id=jid,
        replace_existing=True,
    )
    return jid


def cancel_case_jobs(scheduler: BaseScheduler, case_id: int) -> int:
    prefix = f"case-{case_id}-step-"
    jobs = [j for j in scheduler.get_jobs() if j.id.startswith(prefix)]
    for j in jobs:
        scheduler.remove_job(j.id)
    return len(jobs)


def add_daily_deadline_scan(scheduler: BaseScheduler, hour: int = 9) -> None:
    scheduler.add_job(
        "escalate.scheduler.jobs:scan_deadlines",
        trigger="cron",
        hour=hour,
        minute=0,
        id=DEADLINE_SCAN_ID,
        replace_existing=True,
    )


def scan_case_deadlines(session: Session, case: Case) -> list[Event]:
    """Log one `deadline_warning` per deadline per day while <= warn_when_days_left remain."""
    from escalate.agent.deadlines import deadline_status
    from escalate.playbooks.loader import PlaybookError, get_playbook

    if not case.playbook_id:
        return []
    try:
        pb = get_playbook(case.playbook_id)
    except PlaybookError:
        return []
    today = utcnow().date().isoformat()
    already = {
        (e.payload.get("deadline"), e.payload.get("on"))
        for e in case.events
        if e.type == "deadline_warning"
    }
    created = []
    for st in deadline_status(case, pb):
        if not (st.warn or st.late) or (st.id, today) in already:
            continue
        payload = {
            "deadline": st.id,
            "on": today,
            "due": st.due.isoformat() if st.due else None,
            "days_left": st.days_left,
            "late": st.late,
            "message": (
                f"deadline in {st.days_left} days" if not st.late else "deadline has passed"
            ),
            "rule": st.rule,
        }
        created.append(log_event(session, case.id, "deadline_warning", payload))
    return created


def scan_deadlines() -> int:
    """Daily job: warn about deadlines for every active case."""
    count = 0
    with session_scope() as s:
        for case in s.scalars(select(Case).where(Case.status.in_([str(x) for x in ACTIVE]))):
            count += len(scan_case_deadlines(s, case))
    return count


DEMO_CLEANUP_ID = "demo-cleanup"


def add_demo_cleanup(scheduler: BaseScheduler) -> None:
    scheduler.add_job(
        "escalate.scheduler.jobs:cleanup_demo_cases",
        trigger="interval",
        hours=1,
        id=DEMO_CLEANUP_ID,
        replace_existing=True,
    )


def cleanup_demo_cases() -> list[int]:
    """DEMO_MODE: delete every case older than DEMO_RETENTION_HOURS."""
    s = get_settings()
    if not s.demo_mode:
        return []
    cutoff = utcnow() - timedelta(hours=s.demo_retention_hours)
    with session_scope() as session:
        ids = list(session.scalars(select(Case.id).where(Case.created_at < cutoff)))
    runner = importlib.import_module("escalate.agent.runner")
    for cid in ids:
        runner.delete_case(cid)
    return ids
