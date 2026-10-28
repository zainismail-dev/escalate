"""Typed view of a playbook YAML file (the JSON Schema in schema/ is the contract)."""

import re
from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field

GENERIC_COUNTRY = "INTL"
_WHEN = re.compile(r"^\s*([a-z][a-z0-9_]*)\s+is\s+(not\s+)?set\s*$")


class Deadline(BaseModel):
    id: str
    rule: str
    days: int | None = None
    from_fact: str | None = None  # clock starts on this fact's date ...
    from_step: str | None = None  # ... or when this step's wait runs out with no remedy
    warn_when_days_left: int = 10


class Step(BaseModel):
    id: str
    name: str | None = None
    channel: str
    template: str
    recipient_role: str | None = None
    recipient_fact: str | None = None  # fact holding the address, e.g. seller_contact
    requires: list[str] = Field(default_factory=list)  # extra facts this step needs
    wait_days: int | None = None
    on_no_reply: str | None = None
    on_refused: str | None = None
    on_partial: str | None = None
    when: str | None = None
    proof_required: str | None = None
    attachments: list[str] = Field(default_factory=list)
    adds_if_late: str | None = None

    @property
    def title(self) -> str:
        return self.name or self.id.split("_", 1)[-1].replace("_", " ")

    def applies(self, facts: dict[str, str]) -> bool:
        """Evaluate `when` ("<fact> is set" / "<fact> is not set")."""
        if not self.when:
            return True
        m = parse_when(self.when)
        if m is None:
            return False
        key, negated = m
        present = bool(str(facts.get(key, "")).strip())
        return present != negated


class Source(BaseModel):
    title: str
    url: str | None = None
    note: str | None = None


class Playbook(BaseModel):
    id: str
    version: str
    country: str
    regions: list[str] = Field(default_factory=list)
    sector: str | None = None
    company: str | None = None
    case_type: str
    generic: bool = False
    last_verified: date
    required_facts: list[str]
    optional_facts: list[str] = Field(default_factory=list)
    deadlines: list[Deadline] = Field(default_factory=list)
    steps: list[Step]
    sources: list[Source]
    path: Path | None = Field(default=None, exclude=True)

    @property
    def all_facts(self) -> list[str]:
        return [*self.required_facts, *self.optional_facts]

    def step(self, step_id: str) -> Step:
        for s in self.steps:
            if s.id == step_id:
                return s
        raise KeyError(f"{self.id} has no step {step_id!r}")

    def first_step(self, facts: dict[str, str]) -> Step:
        return next(s for s in self.steps if s.applies(facts))


def parse_when(expr: str) -> tuple[str, bool] | None:
    m = _WHEN.match(expr)
    return (m.group(1), bool(m.group(2))) if m else None


def template_file(templates_dir: Path, ref: str, language: str) -> Path | None:
    """`pk/legal_notice.md.j2` -> templates/pk/<language>/legal_notice.md.j2, falling back to the
    primary language of a BCP-47 tag (`ur-PK` -> `ur`), then en."""
    pack, _, name = ref.partition("/")
    primary = language.replace("_", "-").split("-")[0].lower()
    for lang in dict.fromkeys([language, primary, "en"]):
        p = Path(templates_dir) / pack / lang / name
        if p.is_file():
            return p
    return None


def template_languages(templates_dir: Path, ref: str) -> list[str]:
    pack, _, name = ref.partition("/")
    root = Path(templates_dir) / pack
    if not root.is_dir():
        return []
    return sorted(d.name for d in root.iterdir() if (d / name).is_file())
