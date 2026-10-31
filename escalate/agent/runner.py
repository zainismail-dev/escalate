"""Drive the case graph. The API and the scheduler call these functions, never the graph directly.

Each resume_* function first does its DB work (approve, reject, record a reply, ...) in its own
committed transaction, then resumes the graph. Approval itself is only ever done by
`approve_message`; resuming the graph with "approve" is not enough to send, because the `send`
node checks the DB row.
"""

import functools
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from apscheduler.schedulers.base import BaseScheduler
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from escalate.agent.approval import approve_message, edit_message, reject_message
from escalate.agent.graph import CaseState, compile_graph, compile_with, postgres_checkpointer
from escalate.agent.judge_reply import record_reply
from escalate.channels import confirm_delivery as confirm_delivery_svc
from escalate.config import get_settings
from escalate.db.events import log_event
from escalate.db.models import Case, CaseStatus, Evidence
from escalate.db.session import session_scope
from escalate.scheduler import jobs


class RunnerError(Exception):
    """The case is not waiting for this kind of input."""


@dataclass
class RunResult:
    case_id: int
    pending: dict[str, Any] | None  # the interrupt the case is paused on, if any
    warnings: list[str] | None = None

    @property
    def waiting_for(self) -> str | None:
        return self.pending.get("type") if self.pending else None


_graph: CompiledStateGraph[CaseState] | None = None
_scheduler: BaseScheduler | None = None
_lock = threading.RLock()  # around graph invocations
_case_locks: dict[int, threading.RLock] = {}
_case_locks_guard = threading.Lock()


def case_lock(case_id: int) -> threading.RLock:
    """One lock per case: "what is it waiting for?", the change and the resume happen as one
    step, so two requests (a double click, parallel approves) can't both act on one pause."""
    with _case_locks_guard:
        return _case_locks.setdefault(case_id, threading.RLock())


def _serialised[**P, R](fn: Callable[P, R]) -> Callable[P, R]:
    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        case_id = args[0] if args else kwargs["case_id"]
        with case_lock(int(case_id)):  # type: ignore[call-overload]
            return fn(*args, **kwargs)

    return wrapper


def configure(checkpoint_path: Path | str | None = None) -> CompiledStateGraph[CaseState]:
    """SQLite checkpoints (CHECKPOINT_DB, or `checkpoint_path`); hosted mode: Postgres."""
    global _graph
    s = get_settings()
    if checkpoint_path is None and s.hosted:
        _graph = compile_with(postgres_checkpointer(s.database_url, s.db_schema))
    else:
        _graph = compile_graph(checkpoint_path or s.checkpoint_db)
    return _graph


def graph() -> CompiledStateGraph[CaseState]:
    return _graph or configure()


def set_scheduler(scheduler: BaseScheduler | None) -> None:
    global _scheduler
    _scheduler = scheduler


def schedule_wake(case_id: int, step_id: str, when: datetime) -> None:
    if _scheduler is not None:
        jobs.schedule_wake(_scheduler, case_id, step_id, when)


def _cfg(case_id: int) -> RunnableConfig:
    return {"configurable": {"thread_id": str(case_id)}}


def pending(case_id: int) -> dict[str, Any] | None:
    snap = graph().get_state(_cfg(case_id))
    interrupts = getattr(snap, "interrupts", ()) or ()
    return dict(interrupts[0].value) if interrupts else None


def _run(case_id: int, inp: Any) -> RunResult:
    with _lock:
        graph().invoke(inp, _cfg(case_id))
        return RunResult(case_id, pending(case_id))


def _expect(case_id: int, kind: str) -> dict[str, Any]:
    p = pending(case_id)
    if not p or p.get("type") != kind:
        got = p.get("type") if p else "nothing"
        raise RunnerError(f"case {case_id} is waiting for {got}, not {kind}")
    return p


# --- entry points -------------------------------------------------------------------


@_serialised
def start_case(case_id: int) -> RunResult:
    with session_scope() as s:
        log_event(s, case_id, "case_started", {})
    return _run(case_id, {"case_id": case_id})


@_serialised
def retry(case_id: int) -> RunResult:
    """Re-run the node that failed (e.g. SMTP was down)."""
    return _run(case_id, None)


@_serialised
def resume_with_answers(case_id: int, answers: dict[str, str]) -> RunResult:
    _expect(case_id, "questions")
    return _run(case_id, Command(resume=answers))


@_serialised
def acknowledge_checklist(case_id: int) -> RunResult:
    _expect(case_id, "urgent_checklist")
    return _run(case_id, Command(resume={"ack": True}))


@_serialised
def resume_with_decision(
    case_id: int,
    decision: str,
    edited_body: str | None = None,
    edited_subject: str | None = None,
    reason: str = "",
    recipient: str | None = None,
    message_id: int | None = None,
) -> RunResult:
    p = _expect(case_id, "approve_draft")
    msg_id = int(p["draft"]["message_id"])
    if message_id is not None and message_id != msg_id:
        raise RunnerError(f"message {message_id} is not the draft waiting for approval")
    warnings: list[str] | None = None
    with session_scope() as s:
        if decision == "approve":
            # may raise UnsupportedFacts or RecipientNotConfirmed
            approve_message(s, msg_id, edited_body, edited_subject, recipient=recipient)
        elif decision == "reject":
            reject_message(s, msg_id, reason)
        elif decision == "edit":
            if edited_body is None:
                raise RunnerError("an edit needs the new body")
            warnings = edit_message(s, msg_id, edited_body, edited_subject)
        else:
            raise RunnerError(f"unknown decision {decision!r}")
    result = _run(case_id, Command(resume={"decision": decision, "reason": reason}))
    result.warnings = warnings
    return result


@_serialised
def confirm_delivery(case_id: int, proof_evidence_id: int | None = None) -> RunResult:
    p = _expect(case_id, "confirm_delivery")
    with session_scope() as s:
        proof = s.get(Evidence, proof_evidence_id) if proof_evidence_id else None
        if proof_evidence_id and (proof is None or proof.case_id != case_id):
            raise RunnerError("that proof of delivery is not evidence on this case")
        confirm_delivery_svc(s, int(p["message_id"]), proof)
    return _run(case_id, Command(resume={"confirmed": True}))


@_serialised
def resume_with_reply(case_id: int, text: str) -> RunResult:
    p = _expect(case_id, "waiting_reply")
    with session_scope() as s:
        case = s.get(Case, case_id)
        assert case is not None
        record_reply(s, case, text, step_id=p.get("step"))
    if _scheduler is not None:
        jobs.cancel_case_jobs(_scheduler, case_id)
    return _run(case_id, Command(resume={"text": text}))


@_serialised
def confirm_resolution(case_id: int, resolved: bool, verdict: str | None = None) -> RunResult:
    """The user's answer to a "resolved" verdict: close the case, or continue with `verdict`."""
    _expect(case_id, "confirm_resolution")
    if not resolved and verdict == "resolved":
        raise RunnerError("choose another verdict when the case is not resolved")
    return _run(case_id, Command(resume={"resolved": resolved, "verdict": verdict}))


@_serialised
def resume_timeout(case_id: int, step_id: str) -> RunResult | None:
    """Scheduler wake-up. Ignored if the case moved on (reply logged, withdrawn, ...)."""
    p = pending(case_id)
    if not p or p.get("type") != "waiting_reply" or p.get("step") != step_id:
        return None
    with session_scope() as s:
        case = s.get(Case, case_id)
        if case is None or case.status == CaseStatus.WITHDRAWN:
            return None
        log_event(s, case_id, "wait_expired", {"step": step_id})
    return _run(case_id, Command(resume={"text": None}))


@_serialised
def override_verdict(case_id: int, verdict: str) -> RunResult:
    """Replace the verdict on the last judged reply and replay the ladder from there.

    Uses the graph checkpoint taken just before `judge_reply`. Drafts made after the old verdict
    are rejected (never sent); nothing is approved here.
    """
    with _lock:
        target = None
        for snap in graph().get_state_history(_cfg(case_id)):
            if snap.next == ("judge_reply",):
                target = snap
                break
        if target is None:
            raise RunnerError(f"case {case_id} has no judged reply to correct")
        with session_scope() as s:
            case = s.get(Case, case_id)
            if case is None or case.status == CaseStatus.WITHDRAWN:
                raise RunnerError(f"case {case_id} cannot be changed")
            old = target.values.get("reply_verdict")
            for m in case.messages:
                if m.direction == "out" and m.status == "draft":
                    reject_message(s, m.id, f"verdict changed to {verdict}")
            if verdict == "resolved":
                case.status, case.next_action_at = CaseStatus.RESOLVED, None
                log_event(s, case_id, "case_resolved", {"step": target.values.get("step_id")})
            elif case.status == CaseStatus.RESOLVED:
                case.status = CaseStatus.PICK_NEXT
            log_event(
                s,
                case_id,
                "verdict_overridden",
                {"from": old, "to": verdict, "step": target.values.get("step_id")},
            )
        # The user's own "resolved" needs no second confirmation: replay as if they confirmed it.
        node = "confirm_resolution" if verdict == "resolved" else "judge_reply"
        cfg = graph().update_state(target.config, {"reply_verdict": verdict}, as_node=node)
        graph().invoke(None, cfg)
        return RunResult(case_id, pending(case_id))


def withdraw(case_id: int, reason: str = "") -> None:
    with session_scope() as s:
        case = s.get(Case, case_id)
        if case is None:
            raise RunnerError(f"case {case_id} not found")
        case.status = CaseStatus.WITHDRAWN
        case.next_action_at = None
        log_event(s, case_id, "case_withdrawn", {"reason": reason})
    if _scheduler is not None:
        jobs.cancel_case_jobs(_scheduler, case_id)


def delete_case(case_id: int) -> None:
    """One-click deletion: scheduler jobs, graph checkpoint, evidence files, then DB rows."""
    from escalate.evidence.store import delete_case_files

    if _scheduler is not None:
        jobs.cancel_case_jobs(_scheduler, case_id)
    delete_thread(case_id)
    with session_scope() as s:
        delete_case_files(s, case_id)
    with session_scope() as s:
        case = s.get(Case, case_id)
        if case is None:
            raise RunnerError(f"case {case_id} not found")
        s.delete(case)  # facts, evidence, messages and events cascade


def scrub_checkpoints() -> None:
    """After delete-all: no checkpoint may survive, and the file keeps no trace of them."""
    with _lock:
        saver = graph().checkpointer
        conn = getattr(saver, "conn", None)
        if not isinstance(conn, sqlite3.Connection):
            return
        saver.setup()  # type: ignore[union-attr]  # tables are created lazily: maybe none yet
        with saver.lock:  # type: ignore[union-attr]
            conn.execute("DELETE FROM checkpoints")
            conn.execute("DELETE FROM writes")
            conn.commit()
            conn.execute("VACUUM")
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def delete_thread(case_id: int) -> None:
    """Forget the graph checkpoint for a deleted case."""
    with _lock:
        saver = graph().checkpointer
        if saver is not None and hasattr(saver, "delete_thread"):
            saver.delete_thread(str(case_id))
