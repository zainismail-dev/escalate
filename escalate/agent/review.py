"""What the review screen shows for a draft: verified facts and blanks highlighted in the text,
the facts with their source file, and the safety checks that gate approval.

Blanks are `[[what to fill in]]` or a run of four or more underscores. A draft with a blank
cannot be approved (`approval.approve_message` refuses it too)."""

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from escalate.agent.fact_check import code_check, find_dates, find_ids
from escalate.agent.tone import tone_flags
from escalate.db.models import Case, Message
from escalate.i18n.formatting import format_date, format_money, locale_for
from escalate.pii import mask_pii

BLANK = re.compile(r"\[\[\s*([^\]\n]+?)\s*\]\]|_{4,}")
_ISSUE = re.compile(r"^(date|ID|number) (\S+) is not in the case facts$")

SegmentKind = Literal["text", "fact", "blank"]


@dataclass
class Segment:
    text: str
    kind: SegmentKind = "text"
    key: str | None = None


@dataclass
class Check:
    id: str
    ok: bool
    detail: list[str] = field(default_factory=list)


@dataclass
class Problem:
    """A fact-check issue: the value in the draft and the case facts it should match."""

    kind: str
    wrong: str
    expected: list[str]  # fact keys of the same kind


def blanks(text: str) -> list[str]:
    return [m.group(1) or m.group(0) for m in BLANK.finditer(text)]


def fact_displays(case: Case) -> dict[str, list[str]]:
    """Each fact's raw value plus how a letter in the case's locale writes it."""
    locale = locale_for(case.language, case.country)
    out: dict[str, list[str]] = {}
    for f in case.facts:
        forms = [f.value]
        if f.key == "amount" and case.currency:
            forms.append(format_money(f.value, case.currency, locale))
        if _is_iso_date(f.value):
            forms.append(format_date(f.value, locale))
        out[f.key] = [v for v in dict.fromkeys(forms) if v.strip()]
    return out


def _is_iso_date(v: str) -> bool:
    try:
        date.fromisoformat(v.strip()[:10])
    except ValueError:
        return False
    return len(v.strip()) >= 10


def segments(text: str, displays: dict[str, list[str]]) -> list[Segment]:
    """Split `text` into plain text, verified facts and blanks (longest match first)."""
    spans: list[tuple[int, int, SegmentKind, str | None]] = [
        (m.start(), m.end(), "blank", None) for m in BLANK.finditer(text)
    ]
    needles = sorted(
        ((v, k) for k, vs in displays.items() for v in vs if len(v) >= 3),
        key=lambda p: -len(p[0]),
    )
    for value, key in needles:
        for m in re.finditer(re.escape(value), text):
            if all(m.end() <= s or m.start() >= e for s, e, _, _ in spans):
                spans.append((m.start(), m.end(), "fact", key))
    spans.sort()
    out: list[Segment] = []
    pos = 0
    for start, end, kind, fact_key in spans:
        if start > pos:
            out.append(Segment(text[pos:start]))
        out.append(Segment(text[start:end], kind, fact_key))
        pos = end
    if pos < len(text):
        out.append(Segment(text[pos:]))
    return out


def problems(issues: list[str], facts: dict[str, str]) -> list[Problem]:
    out = []
    for issue in issues:
        m = _ISSUE.match(issue)
        if not m:
            continue
        kind, wrong = m.group(1).lower(), m.group(2)
        out.append(Problem(kind, wrong, _same_kind(kind, facts)))
    return out


def _same_kind(kind: str, facts: dict[str, str]) -> list[str]:
    if kind == "date":
        return [k for k, v in facts.items() if find_dates(v) or _is_iso_date(v)]
    if kind == "id":
        return [k for k, v in facts.items() if k.endswith("_id") or find_ids(v)]
    return [k for k, v in facts.items() if re.fullmatch(r"[\d,.\s]+", v.strip())]


def checks(msg: Message, reference: str, notice: str) -> tuple[list[Check], list[str]]:
    """The checks approval enforces (facts, blanks) plus tone, the not-legal-advice notice and
    no unmasked card numbers, IBANs, IDs or codes. Returns (checks, raw fact-check issues)."""
    text = f"{msg.subject or ''}\n{msg.body}"
    issues = code_check(text, msg.case.fact_dict(), reference)
    tone = tone_flags(text)
    return [
        Check("facts", not issues, issues),
        Check("blanks", not blanks(text), blanks(text)),
        Check("tone", not tone, tone),
        Check("disclaimer", notice.strip("-\n ") in text),
        Check("no_secrets", mask_pii(text) == text),
    ], issues
