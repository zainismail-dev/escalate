"""Judge a company's reply (section 8, prompt 4) and record it in the case."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from escalate.db.events import log_event
from escalate.db.models import Case, Message, utcnow
from escalate.llm import LLM, get_llm
from escalate.llm.prompts import render_prompt
from escalate.llm.structured import ask_json
from escalate.pii import mask_pii

Verdict = Literal["resolved", "partial", "refused", "no_reply"]


class Judgement(BaseModel):
    verdict: Verdict
    promise: str | None = None
    promise_date: date | None = None
    reason: str = ""

    @field_validator("promise", "promise_date", mode="before")
    @classmethod
    def _blank_is_none(cls, v: object) -> object:
        return None if isinstance(v, str) and v.strip().lower() in ("", "null", "none") else v


def judge(reply_text: str | None, remedy_wanted: str, llm: LLM | None = None) -> Judgement:
    """No reply text (the timer fired) is `no_reply` without asking the model."""
    if reply_text is None or not reply_text.strip():
        return Judgement(verdict="no_reply", reason="no reply before the deadline")
    prompt = render_prompt(
        "judge_reply", remedy_wanted=remedy_wanted, reply_text=reply_text.strip()
    )
    j = ask_json(llm or get_llm(), prompt, Judgement, slot="fast")
    # Code-side rule: a promise without a date is not a remedy, whatever the model said.
    if j.promise and j.promise_date is None and j.verdict in ("resolved", "partial"):
        return j.model_copy(
            update={"verdict": "refused", "reason": f"undated promise: {j.promise}"}
        )
    return j


def record_reply(session: Session, case: Case, text: str, step_id: str | None = None) -> Message:
    msg = Message(
        case_id=case.id,
        step_id=step_id or case.current_step or "reply",
        direction="in",
        channel="email",
        body=mask_pii(text.strip()),
        status="received",
        sent_at=utcnow(),
    )
    session.add(msg)
    case.messages.append(msg)
    session.flush()
    log_event(session, case.id, "reply_logged", {"message_id": msg.id, "step": msg.step_id})
    return msg


def log_verdict(session: Session, case: Case, j: Judgement, step_id: str | None) -> None:
    payload = j.model_dump(mode="json")
    payload["step"] = step_id
    log_event(session, case.id, "reply_judged", payload)
