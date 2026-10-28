"""Intake: extract case facts from the user's words and evidence text (section 8, prompt 1)."""

from dataclasses import dataclass, field

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from escalate.db.events import log_event
from escalate.db.models import Case, CaseFact
from escalate.llm import LLM, get_llm
from escalate.llm.prompts import render_prompt
from escalate.llm.structured import ask_json

MIN_CONFIDENCE = 0.5  # below this the model is guessing: ask the user instead


class ExtractedFact(BaseModel):
    value: str
    evidence_id: int | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)

    @field_validator("value", mode="before")
    @classmethod
    def _stringify(cls, v: object) -> object:
        return v if isinstance(v, str) or v is None else str(v)


class Extraction(BaseModel):
    facts: dict[str, ExtractedFact] = Field(default_factory=dict)
    missing: list[str] = Field(default_factory=list)

    @field_validator("facts", mode="before")
    @classmethod
    def _drop_nulls(cls, v: object) -> object:
        if isinstance(v, dict):
            return {
                k: f
                for k, f in v.items()
                if isinstance(f, dict) and f.get("value") not in (None, "")
            }
        return v


@dataclass
class IntakeResult:
    facts: dict[str, str]
    missing: list[str]
    saved: list[str] = field(default_factory=list)


def evidence_blocks(evidence: list[tuple[int, str]]) -> str:
    if not evidence:
        return "(none)"
    return "\n".join(f"[evidence_id={eid}]\n{text.strip()}\n[/evidence]" for eid, text in evidence)


def extract(
    session: Session,
    case: Case,
    user_text: str,
    evidence_texts: list[tuple[int, str]],
    required_facts: list[str],
    optional_facts: list[str] | None = None,
    llm: LLM | None = None,
) -> IntakeResult:
    """Ask the smart model for facts, store the confident ones, and list what is still missing."""
    optional = [k for k in (optional_facts or []) if k not in required_facts]
    prompt = render_prompt(
        "extract_facts",
        required_facts=", ".join(required_facts),
        optional_facts=", ".join(optional) or "(none)",
        user_text=user_text.strip(),
        evidence_blocks=evidence_blocks(evidence_texts),
    )
    result = ask_json(llm or get_llm(), prompt, Extraction, slot="smart")

    allowed = set(required_facts) | set(optional)
    valid_evidence = {eid for eid, _ in evidence_texts}
    existing = {f.key: f for f in case.facts}
    saved: list[str] = []
    for key, fact in result.facts.items():
        value = fact.value.strip()
        if key not in allowed or not value or fact.confidence < MIN_CONFIDENCE:
            continue
        old = existing.get(key)
        if old is not None and old.confidence > fact.confidence:
            continue  # e.g. the user typed it in themselves
        src = fact.evidence_id if fact.evidence_id in valid_evidence else None
        if old is None:
            old = CaseFact(case_id=case.id, key=key, value=value)
            session.add(old)
            case.facts.append(old)
            existing[key] = old
        old.value, old.source_evidence_id, old.confidence = value, src, fact.confidence
        saved.append(key)

    facts = {k: f.value for k, f in existing.items()}
    missing = [k for k in required_facts if not facts.get(k, "").strip()]
    session.flush()
    log_event(session, case.id, "facts_extracted", {"saved": sorted(saved), "missing": missing})
    return IntakeResult(facts=facts, missing=missing, saved=saved)


def save_answers(session: Session, case: Case, answers: dict[str, str]) -> list[str]:
    """Store the user's own answers to missing-fact questions (confidence 1.0)."""
    existing = {f.key: f for f in case.facts}
    saved = []
    for key, raw in answers.items():
        value = (raw or "").strip()
        if not value:
            continue
        fact = existing.get(key)
        if fact is None:
            fact = CaseFact(case_id=case.id, key=key, value=value)
            session.add(fact)
            case.facts.append(fact)
        fact.value, fact.confidence, fact.source_evidence_id = value, 1.0, None
        saved.append(key)
    session.flush()
    log_event(session, case.id, "answers_saved", {"keys": sorted(saved)})
    return saved
