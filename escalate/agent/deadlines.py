"""Compute legal deadlines (e.g. a 30-day court filing limit) from facts and sent messages."""

from dataclasses import dataclass
from datetime import date, timedelta

from escalate.db.models import Case, utcnow
from escalate.playbooks.models import Deadline, Playbook


@dataclass
class DeadlineStatus:
    id: str
    rule: str
    due: date | None
    days_left: int | None
    warn: bool
    late: bool


def _parse(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value.strip()[:10]) if value else None
    except ValueError:
        return None


def start_date(case: Case, pb: Playbook, dl: Deadline) -> date | None:
    facts = case.fact_dict()
    if dl.from_fact and (d := _parse(facts.get(dl.from_fact))):
        return d
    if dl.from_step:
        sent = [
            m
            for m in case.messages
            if m.step_id == dl.from_step and m.sent_at and m.direction == "out"
        ]
        if sent:
            wait = pb.step(dl.from_step).wait_days or 0
            return sent[-1].sent_at.date() + timedelta(days=wait)  # type: ignore[union-attr]
    return None


def deadline_status(case: Case, pb: Playbook, today: date | None = None) -> list[DeadlineStatus]:
    today = today or utcnow().date()
    out = []
    for dl in pb.deadlines:
        start = start_date(case, pb, dl)
        due = start + timedelta(days=dl.days) if start and dl.days else None
        left = (due - today).days if due else None
        out.append(
            DeadlineStatus(
                id=dl.id,
                rule=dl.rule,
                due=due,
                days_left=left,
                warn=left is not None and 0 <= left <= dl.warn_when_days_left,
                late=left is not None and left < 0,
            )
        )
    return out


def is_late(case: Case, pb: Playbook, today: date | None = None) -> bool:
    return any(d.late for d in deadline_status(case, pb, today))
