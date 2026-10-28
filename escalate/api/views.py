"""Read models for the web app: the escalation ladder and why the agent picked the current step.

Reasons are codes plus parameters, not sentences, so every UI language can word them."""

from typing import Any

from escalate.agent.deadlines import deadline_status
from escalate.db.models import Case
from escalate.playbooks.models import GENERIC_COUNTRY, Playbook


def pack_level(pb: Playbook, case: Case) -> str:
    """Which resolver level picked this playbook: company, region, country or generic."""
    if pb.company:
        return "company"
    if pb.generic or pb.country == GENERIC_COUNTRY:
        return "generic"
    if pb.regions and case.region in pb.regions:
        return "region"
    return "country"


def ladder(pb: Playbook, case: Case) -> list[dict[str, Any]]:
    """Every rung with its state: done, current, future or skipped (its `when` does not hold)."""
    facts = case.fact_dict()
    ids = [s.id for s in pb.steps]
    current = ids.index(case.current_step) if case.current_step in ids else -1
    finished = case.status in ("resolved", "closed_unresolved")
    out = []
    for i, s in enumerate(pb.steps):
        if i == current:
            state = "done" if finished else "current"
        elif not s.applies(facts):
            state = "skipped"
        else:
            state = "done" if i < current else "future"
        out.append(
            {
                "id": s.id,
                "name": s.title,
                "channel": s.channel,
                "recipient_role": s.recipient_role,
                "wait_days": s.wait_days,
                "state": state,
            }
        )
    return out


def reasons(pb: Playbook, case: Case) -> list[dict[str, Any]]:
    """Why the case is on its current step, most important first."""
    if not case.current_step:
        return []
    step = pb.step(case.current_step)
    rungs = ladder(pb, case)
    live = [r for r in rungs if r["state"] != "skipped"]
    pos = next((i + 1 for i, r in enumerate(live) if r["id"] == step.id), None)
    out: list[dict[str, Any]] = []
    judged = [e for e in case.events if e.type in ("reply_judged", "wait_expired")]
    if judged:
        last = judged[-1]
        prev = last.payload.get("step")
        if prev and prev != step.id:
            prev_name = pb.step(prev).title if prev in {s.id for s in pb.steps} else prev
            verdict = "no_reply" if last.type == "wait_expired" else last.payload.get("verdict")
            out.append(
                {
                    "code": "after_verdict",
                    "params": {
                        "verdict": verdict,
                        "step": prev_name,
                        "reason": last.payload.get("reason") or "",
                    },
                }
            )
    elif pos == 1:
        out.append({"code": "first_step", "params": {}})
    for r in rungs:
        if r["state"] == "skipped":
            out.append({"code": "skipped", "params": {"step": r["name"]}})
    out.append({"code": "position", "params": {"n": pos or 1, "total": len(live)}})
    out.append(
        {
            "code": "channel",
            "params": {"channel": step.channel, "recipient": step.recipient_role or ""},
        }
    )
    if step.wait_days:
        out.append({"code": "wait", "params": {"days": step.wait_days}})
    if step.proof_required:
        out.append({"code": "proof", "params": {"proof": step.proof_required}})
    for d in deadline_status(case, pb):
        if d.warn or d.late:
            out.append(
                {
                    "code": "deadline_late" if d.late else "deadline",
                    "params": {"rule": d.rule, "days_left": d.days_left},
                }
            )
    out.append(
        {
            "code": "playbook",
            "params": {"playbook": pb.id, "version": pb.version, "level": pack_level(pb, case)},
        }
    )
    return out
