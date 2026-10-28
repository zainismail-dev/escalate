"""The case graph (section 7). One LangGraph thread per case, `thread_id = str(case_id)`.

Nodes do their DB work in their own session and only keep small values in the state. The graph
pauses with `interrupt()` for: missing-fact questions, the scam checklist, draft approval, the
user's delivery confirmation (post/court/web form) and the wait for a reply.

Sending is only possible in `send`, which goes through `escalate.channels.send_message`, which
refuses unless the DB row has `approved_at` set (CLAUDE.md rule 1).
"""

import sqlite3
from datetime import timedelta
from pathlib import Path
from typing import Any, Literal, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from escalate.agent import classify as classify_svc
from escalate.agent import deadlines
from escalate.agent.draft import draft_step, template_text
from escalate.agent.fact_check import fact_check as run_fact_check
from escalate.agent.intake import extract, save_answers
from escalate.agent.judge_reply import judge, log_verdict
from escalate.agent.pick_next import pick_next as pick_next_step
from escalate.channels import send_message
from escalate.db.events import log_event
from escalate.db.models import Case, CaseStatus, Message
from escalate.db.session import session_scope
from escalate.llm.structured import StructuredOutputError
from escalate.playbooks.loader import get_playbook
from escalate.playbooks.models import Playbook, Step
from escalate.templates_engine import MissingFacts, missing_for_step

MAX_QUESTIONS = 5
MAX_DRAFT_ATTEMPTS = 3  # after this, the plain facts-only template is used


class CaseState(TypedDict, total=False):
    case_id: int
    case_type: str
    facts: dict[str, str]
    missing: list[str]
    extracted: bool
    playbook_id: str
    step_id: str
    checklist_done: bool
    draft: dict[str, Any]  # {message_id, recipient, subject, body}
    message_id: int
    attempts: int
    template_only: bool
    fact_ok: bool
    issues: list[str]
    decision: Literal["approve", "edit", "reject"]
    last_reply: str | None
    reply_verdict: Literal["resolved", "partial", "refused", "no_reply"]
    late: bool
    done: str


# --- helpers ----------------------------------------------------------------------


def _case(s: Any, state: CaseState) -> Case:
    case = s.get(Case, state["case_id"])
    if case is None:
        raise LookupError(f"case {state['case_id']} not found")
    return case


def _step(pb: Playbook, state: CaseState, facts: dict[str, str]) -> Step:
    return pb.step(state["step_id"]) if state.get("step_id") else pb.first_step(facts)


def _draft_dict(msg: Message) -> dict[str, Any]:
    return {
        "message_id": msg.id,
        "recipient": msg.recipient,
        "subject": msg.subject,
        "body": msg.body,
        "channel": msg.channel,
    }


# --- nodes ------------------------------------------------------------------------


def intake(state: CaseState) -> CaseState:
    with session_scope() as s:
        case = _case(s, state)
        if not case.case_type or not case.playbook_id:
            classify_svc.classify(s, case)
        pb = get_playbook(case.playbook_id or "")
        if not state.get("extracted"):
            evidence = [(e.id, e.extracted_text or "") for e in case.evidence if e.extracted_text]
            try:
                extract(s, case, case.description, evidence, pb.required_facts, pb.optional_facts)
            except StructuredOutputError as exc:  # the user will be asked instead
                log_event(s, case.id, "extraction_failed", {"error": str(exc)[:300]})
        facts = case.fact_dict()
        missing = missing_for_step(pb, _step(pb, state, facts), facts)
        case.status = CaseStatus.INTAKE if missing else case.status
        return {
            "case_type": case.case_type or "",
            "playbook_id": pb.id,
            "facts": facts,
            "missing": missing,
            "extracted": True,
        }


def ask_missing(state: CaseState) -> CaseState:
    questions = state.get("missing", [])[:MAX_QUESTIONS]
    answers = interrupt({"type": "questions", "missing": questions})
    with session_scope() as s:
        save_answers(s, _case(s, state), dict(answers or {}))
    return {}


def classify(state: CaseState) -> CaseState:
    with session_scope() as s:
        case = _case(s, state)
        if state.get("step_id"):
            return {}  # mid-ladder: never switch playbooks under the user
        pb = classify_svc.apply_playbook(s, case)
        facts = case.fact_dict()
        first = pb.first_step(facts)
        case.current_step = first.id
        return {"playbook_id": pb.id, "step_id": first.id, "facts": facts}


def urgent_checklist(state: CaseState) -> CaseState:
    from escalate.agent.checklist import load_checklist

    with session_scope() as s:
        case = _case(s, state)
        case.status = CaseStatus.URGENT
        items = [i.model_dump() for i in load_checklist(case.country).items]
    interrupt({"type": "urgent_checklist", "items": items})
    with session_scope() as s:
        log_event(s, state["case_id"], "urgent_checklist_acknowledged", {})
    return {"checklist_done": True}


def draft(state: CaseState) -> CaseState:
    attempts = state.get("attempts", 0)
    template_only = attempts >= MAX_DRAFT_ATTEMPTS
    with session_scope() as s:
        case = _case(s, state)
        pb = get_playbook(state["playbook_id"])
        step = pb.step(state["step_id"])
        case.status = CaseStatus.DRAFTING
        try:
            msg = draft_step(
                s,
                case,
                pb,
                step,
                feedback=state.get("issues") or None,
                late=state.get("late", False),
                use_llm=not template_only,
            )
        except MissingFacts as exc:
            return {"missing": exc.keys}
        return {
            "missing": [],
            "message_id": msg.id,
            "draft": _draft_dict(msg),
            "template_only": template_only,
        }


def fact_check(state: CaseState) -> CaseState:
    with session_scope() as s:
        case = _case(s, state)
        msg = s.get(Message, state["message_id"])
        assert msg is not None
        pb = get_playbook(state["playbook_id"])
        step = pb.step(state["step_id"])
        reference = template_text(
            case, pb, step, late=state.get("late", False), today=msg.created_at.date()
        )
        result = run_fact_check(
            f"{msg.subject or ''}\n{msg.body}",
            case.fact_dict(),
            reference=reference,
            use_model=not state.get("template_only", False),
        )
        attempts = state.get("attempts", 0) + (0 if result.ok else 1)
        log_event(
            s,
            case.id,
            "fact_checked",
            {"message_id": msg.id, "ok": result.ok, "issues": result.issues},
        )
        if result.ok:
            case.status = CaseStatus.AWAITING_APPROVAL
        return {"fact_ok": result.ok, "issues": result.issues, "attempts": attempts}


def approval(state: CaseState) -> CaseState:
    answer = interrupt({"type": "approve_draft", "draft": state["draft"]})
    decision = answer["decision"]
    update: CaseState = {"decision": decision, "draft": answer.get("draft", state["draft"])}
    if decision == "reject":
        update["issues"] = [f"The user rejected the draft: {answer.get('reason') or 'no reason'}"]
        update["attempts"] = 0
    return update


def send(state: CaseState) -> CaseState:
    msg_id = state["message_id"]
    with session_scope() as s:
        result = send_message(s, msg_id)
        msg = s.get(Message, msg_id)
        assert msg is not None
        delivered = msg.sent_at is not None
        channel = msg.channel
    if not delivered:
        interrupt(
            {
                "type": "confirm_delivery",
                "message_id": msg_id,
                "channel": channel,
                "note": result.note,
            }
        )
    with session_scope() as s:
        msg = s.get(Message, msg_id)
        assert msg is not None and msg.sent_at is not None, "delivery not confirmed"
        case = _case(s, state)
        pb = get_playbook(state["playbook_id"])
        step = pb.step(state["step_id"])
        if step.wait_days is None:
            case.status = CaseStatus.CLOSED_UNRESOLVED
            case.next_action_at = None
            log_event(s, case.id, "ladder_complete", {"step": step.id})
            return {"done": "ladder_complete"}
        when = msg.sent_at + timedelta(days=step.wait_days)
        case.status = CaseStatus.WAITING_REPLY
        case.next_action_at = when
        from escalate.agent import runner

        runner.schedule_wake(case.id, step.id, when)
        log_event(s, case.id, "waiting_reply", {"step": step.id, "until": when.isoformat()})
    return {"done": ""}


def wait(state: CaseState) -> CaseState:
    reply = interrupt({"type": "waiting_reply", "step": state["step_id"]})
    return {"last_reply": (reply or {}).get("text")}  # None when the timer fired


def judge_reply(state: CaseState) -> CaseState:
    with session_scope() as s:
        case = _case(s, state)
        remedy = case.fact_dict().get("remedy_wanted", "")
        j = judge(state.get("last_reply"), remedy)
        log_verdict(s, case, j, state.get("step_id"))
        if j.verdict == "resolved":
            case.status = CaseStatus.RESOLVED
            case.next_action_at = None
            log_event(s, case.id, "case_resolved", {"step": state.get("step_id")})
        return {"reply_verdict": j.verdict}


def pick_next(state: CaseState) -> CaseState:
    with session_scope() as s:
        case = _case(s, state)
        pb = get_playbook(state["playbook_id"])
        facts = case.fact_dict()
        nxt = pick_next_step(pb, state["step_id"], state["reply_verdict"], facts)
        if nxt is None:
            case.status = CaseStatus.CLOSED_UNRESOLVED
            case.next_action_at = None
            log_event(s, case.id, "ladder_complete", {"step": state["step_id"]})
            return {"step_id": "", "done": "ladder_complete"}
        late = deadlines.is_late(case, pb)
        case.current_step = nxt
        case.status = CaseStatus.PICK_NEXT
        log_event(s, case.id, "next_step", {"from": state["step_id"], "to": nxt, "late": late})
        return {"step_id": nxt, "attempts": 0, "issues": [], "late": late, "facts": facts}


# --- wiring -------------------------------------------------------------------------


def build_graph() -> StateGraph[CaseState]:
    g = StateGraph(CaseState)
    for name, fn in [
        ("intake", intake),
        ("ask_missing", ask_missing),
        ("classify", classify),
        ("urgent_checklist", urgent_checklist),
        ("draft", draft),
        ("fact_check", fact_check),
        ("approval", approval),
        ("send", send),
        ("wait", wait),
        ("judge_reply", judge_reply),
        ("pick_next", pick_next),
    ]:
        g.add_node(name, fn)

    g.set_entry_point("intake")
    g.add_conditional_edges("intake", lambda s: "ask_missing" if s.get("missing") else "classify")
    g.add_edge("ask_missing", "intake")
    g.add_conditional_edges(
        "classify",
        lambda s: (
            "urgent_checklist"
            if s.get("case_type") == "scam" and not s.get("checklist_done")
            else "draft"
        ),
    )
    g.add_edge("urgent_checklist", "draft")
    g.add_conditional_edges("draft", lambda s: "ask_missing" if s.get("missing") else "fact_check")
    g.add_conditional_edges("fact_check", lambda s: "approval" if s.get("fact_ok") else "draft")
    g.add_conditional_edges(
        "approval",
        lambda s: {"approve": "send", "edit": "fact_check", "reject": "draft"}[s["decision"]],
    )
    g.add_conditional_edges("send", lambda s: END if s.get("done") else "wait")
    g.add_edge("wait", "judge_reply")
    g.add_conditional_edges(
        "judge_reply", lambda s: END if s["reply_verdict"] == "resolved" else "pick_next"
    )
    g.add_conditional_edges("pick_next", lambda s: "draft" if s.get("step_id") else END)
    return g


def compile_graph(checkpoint_path: Path | str) -> CompiledStateGraph[CaseState]:
    path = str(checkpoint_path)
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    return build_graph().compile(checkpointer=SqliteSaver(conn))
