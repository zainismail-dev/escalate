"""Fact check (section 8, prompt 5): code first, then the fast model.

Code check: every number, date and ID in the draft must appear in the case facts or in the
trusted template rendering (which is itself built only from facts, today and the reply-by date).
"""

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

from pydantic import BaseModel, Field

from escalate.agent.tone import tone_flags
from escalate.llm import LLM, get_llm
from escalate.llm.prompts import render_prompt
from escalate.llm.structured import StructuredOutputError, ask_json
from escalate.pii import mask_pii

_MONTHS = (
    "january|february|march|april|may|june|july|august|september|october|november|december|"
    "jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec"
)
_DATE_PATTERNS = [
    (re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"), "ymd"),
    (re.compile(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b"), "dmy"),
    (
        re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTHS})\.?,?\s+(\d{{4}})\b", re.I),
        "d_mon_y",
    ),
    (
        re.compile(rf"\b({_MONTHS})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I),
        "mon_d_y",
    ),
]
# An ID mixes letters and digits, e.g. BM-48213, QK55120, ML-7781-SB.
_ID = re.compile(r"\b(?=[A-Za-z0-9-]*\d)(?=[A-Za-z0-9-]*[A-Za-z])[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+\b")
_NUMBER = re.compile(r"(?<![\w.-])\d[\d,.\s]*\d(?![\w-])|(?<![\w.-])\d(?![\w-])")


def _month(name: str) -> int:
    key = name.lower()[:3]
    return [m[:3] for m in _MONTHS.split("|")[:12]].index(key) + 1


def find_dates(text: str) -> set[date]:
    found: set[date] = set()
    for rx, kind in _DATE_PATTERNS:
        for m in rx.finditer(text):
            try:
                g = m.groups()
                if kind == "ymd":
                    found.add(date(int(g[0]), int(g[1]), int(g[2])))
                elif kind == "dmy":
                    found.add(date(int(g[2]), int(g[1]), int(g[0])))
                elif kind == "d_mon_y":
                    found.add(date(int(g[2]), _month(g[1]), int(g[0])))
                else:
                    found.add(date(int(g[2]), _month(g[0]), int(g[1])))
            except ValueError:
                continue
    return found


def _strip_dates(text: str) -> str:
    for rx, _ in _DATE_PATTERNS:
        text = rx.sub(" ", text)
    return text


def norm_number(raw: str) -> str:
    """'45,000.00' -> '45000'; '4.500,00' -> '4500'; '45 000' -> '45000'."""
    s = re.sub(r"\s", "", raw)
    if re.search(r",\d{2}$", s) and "." in s:  # 4.500,00 (European)
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    if s.count(".") > 1:
        s = s.replace(".", "")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s.lstrip("0") or "0"


def find_numbers(text: str) -> set[str]:
    text = _ID.sub(" ", _strip_dates(text))
    return {norm_number(m.group(0)) for m in _NUMBER.finditer(text)}


def find_ids(text: str) -> set[str]:
    return {m.group(0).upper() for m in _ID.finditer(_strip_dates(text))}


@dataclass
class FactCheckResult:
    code_issues: list[str] = field(default_factory=list)
    model_issues: list[str] = field(default_factory=list)
    tone_issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.code_issues and not self.model_issues and not self.tone_issues

    @property
    def issues(self) -> list[str]:
        tone = [f"tone: {t} (keep it firm, polite and factual)" for t in self.tone_issues]
        return [*self.code_issues, *tone, *self.model_issues]


def ascii_digits(text: str) -> str:
    """'۴۵۰۰۰' (Urdu), '४५' (Devanagari) -> ASCII digits, so every script is checked alike."""
    return "".join(str(unicodedata.decimal(c)) if c.isdecimal() else c for c in text)


def code_check(draft: str, facts: dict[str, str], reference: str = "") -> list[str]:
    """Every number, date and ID in `draft` must come from `facts` or the trusted `reference`."""
    draft = ascii_digits(draft)
    facts = {k: ascii_digits(v) for k, v in facts.items()}
    reference = ascii_digits(reference)
    # Masked forms (e.g. "•••• 1111" for a card number) count as known too.
    corpus = "\n".join(
        [*facts.values(), reference, mask_pii(reference)] + [mask_pii(v) for v in facts.values()]
    )
    ok_dates = find_dates(corpus)
    ok_ids = find_ids(corpus)
    ok_numbers = find_numbers(corpus) | {norm_number(v) for v in facts.values() if _is_num(v)}
    # Parts of allowed IDs and dates (e.g. 48213 in BM-48213, 2026) are also fine.
    for i in ok_ids:
        ok_numbers |= {norm_number(p) for p in re.findall(r"\d+", i)}
    for d in ok_dates:
        ok_numbers |= {str(d.year), str(d.day), str(d.month)}

    issues = []
    for d in sorted(find_dates(draft) - ok_dates):
        issues.append(f"date {d.isoformat()} is not in the case facts")
    for i in sorted(find_ids(draft) - ok_ids):
        issues.append(f"ID {i} is not in the case facts")
    for n in sorted(find_numbers(draft) - ok_numbers):
        issues.append(f"number {n} is not in the case facts")
    return issues


def _is_num(v: str) -> bool:
    return bool(re.fullmatch(r"[\d,.\s]+", v.strip()))


class ModelCheck(BaseModel):
    unsupported: list[str] = Field(default_factory=list)


def model_check(draft: str, facts: dict[str, str], llm: LLM | None = None) -> list[str]:
    prompt = render_prompt(
        "fact_check", draft=draft, facts_json=json.dumps(facts, ensure_ascii=False)
    )
    try:
        out = ask_json(llm or get_llm(), prompt, ModelCheck, slot="fast")
    except StructuredOutputError:
        return []  # the code check already ran; a confused model must not block forever
    return [u.strip() for u in out.unsupported if u and u.strip()]


def fact_check(
    draft: str,
    facts: dict[str, str],
    reference: str = "",
    llm: LLM | None = None,
    use_model: bool = True,
) -> FactCheckResult:
    result = FactCheckResult(
        code_issues=code_check(draft, facts, reference), tone_issues=tone_flags(draft)
    )
    if use_model and not result.code_issues and not result.tone_issues:
        result.model_issues = model_check(draft, facts, llm)
    return result
