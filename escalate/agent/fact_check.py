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
# An ID mixes letters and digits, e.g. BM-48213, QK55120, ML-7781-SB; `_is_id` checks the mix.
# Bounded (up to 17 parts of 64 characters; a longer one is matched in pieces), so a failed
# attempt can't rescan the rest of the text.
_ID = re.compile(r"\b[A-Za-z0-9]{1,64}(?:-[A-Za-z0-9]{1,64}){1,16}\b")
# A run of digit groups ("45,000.00", "45 000"). Each group starts with a digit, so a run
# matches one way only and nothing after it can fail (a trailing `(?![\w-])` made every start
# rescan the run): `_numbers` checks what follows instead.
_DIGIT_RUN = re.compile(r"(?<![\w.-])\d(?:[,.\s]*\d)*")
_WORDISH = re.compile(r"[\w-]")
# "14-day", "43-inch": a number and a word, not an ID. The number still has to be known. Bounded
# like `_ID`, and only a lower-case word: "123-ABC" stays an ID.
_NUMBER_WORD = re.compile(r"(?<![\w-])(\d{1,12})-[a-z]{1,32}(?![\w-])")
# Reasoning models like U+2011 in "AC-10234" and U+202F in "1 October 2026".
_TYPOGRAPHY = str.maketrans(
    dict.fromkeys("\u2010\u2011", "-") | dict.fromkeys("\u00a0\u2009\u202f", " ")
)


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


def plain_typography(text: str) -> str:
    """Ordinary hyphens and spaces, so IDs and dates stay searchable and copy cleanly."""
    return text.translate(_TYPOGRAPHY)


def _is_id(m: re.Match[str]) -> bool:
    v = m.group(0)
    if _NUMBER_WORD.fullmatch(v):
        return False
    return any(c.isdigit() for c in v) and any(c.isalpha() for c in v)


def _drop_last_group(run: str) -> str:
    """'45 000' -> '45': the last digit group and the separators before it."""
    i = len(run)
    while i and run[i - 1].isdecimal():
        i -= 1
    while i and (run[i - 1] in ",." or run[i - 1].isspace()):
        i -= 1
    return run[:i]


def _numbers(text: str) -> list[str]:
    """Numbers not glued to a word or hyphen: in "45 000abc" the number is "45"."""
    out = []
    for m in _DIGIT_RUN.finditer(text):
        run = m.group(0)
        if _WORDISH.match(text, m.end()):
            run = _drop_last_group(run)
        if run:
            out.append(run)
    return out


def find_numbers(text: str) -> set[str]:
    text = _ID.sub(lambda m: " " if _is_id(m) else m.group(0), _strip_dates(text))
    text = _NUMBER_WORD.sub(r"\1 ", text)
    return {norm_number(n) for n in _numbers(text)}


def find_ids(text: str) -> set[str]:
    return {m.group(0).upper() for m in _ID.finditer(_strip_dates(text)) if _is_id(m)}


@dataclass
class FactCheckResult:
    code_issues: list[str] = field(default_factory=list)
    model_issues: list[str] = field(default_factory=list)
    tone_issues: list[str] = field(default_factory=list)
    omissions: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.code_issues or self.model_issues or self.tone_issues or self.omissions)

    @property
    def issues(self) -> list[str]:
        tone = [f"tone: {t} (keep it firm, polite and factual)" for t in self.tone_issues]
        return [*self.code_issues, *tone, *self.omissions, *self.model_issues]

    @property
    def categories(self) -> list[str]:
        """Why the draft failed, safe to log: categories only, never a value from the case."""
        found = {f"invented_{i.split(' ', 1)[0].lower()}" for i in self.code_issues}
        if self.tone_issues:
            found.add("tone")
        if self.omissions:
            found.add("dropped_value")
        if self.model_issues:
            found.add("model_unsupported")
        return sorted(found)


def ascii_digits(text: str) -> str:
    """'۴۵۰۰۰' (Urdu), '४५' (Devanagari) -> ASCII digits, so every script is checked alike."""
    return "".join(str(unicodedata.decimal(c)) if c.isdecimal() else c for c in text)


def _comparable(text: str) -> str:
    return plain_typography(ascii_digits(text))


def code_check(draft: str, facts: dict[str, str], reference: str = "") -> list[str]:
    """Every number, date and ID in `draft` must come from `facts` or the trusted `reference`."""
    draft = _comparable(draft)
    facts = {k: _comparable(v) for k, v in facts.items()}
    reference = _comparable(reference)
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


def dropped_values(draft: str, reference: str) -> list[str]:
    """A rewrite may reword the letter, but every date, ID and number of the trusted template
    (order number, amount, the days to reply, the reply-by date, the law's year) must survive."""
    draft, reference = _comparable(draft), _comparable(reference)
    gone = [d.isoformat() for d in find_dates(reference) - find_dates(draft)]
    gone += find_ids(reference) - find_ids(draft)
    gone += find_numbers(reference) - find_numbers(draft) - _parts_of_ids_and_dates(draft)
    return [f"keep {value} from the template" for value in sorted(gone)]


def _parts_of_ids_and_dates(text: str) -> set[str]:
    parts = {norm_number(p) for i in find_ids(text) for p in re.findall(r"\d+", i)}
    for d in find_dates(text):
        parts |= {str(d.year), str(d.day), str(d.month)}
    return parts


class ModelCheck(BaseModel):
    unsupported: list[str] = Field(default_factory=list)


def model_check(
    draft: str, facts: dict[str, str], llm: LLM | None = None, reference: str = ""
) -> list[str]:
    prompt = render_prompt(
        "fact_check",
        draft=draft,
        facts_json=json.dumps(facts, ensure_ascii=False),
        reference=reference or "(none)",
    )
    try:
        out = ask_json(llm or get_llm(), prompt, ModelCheck, slot="fast")
    except StructuredOutputError:
        return []  # the code check already ran; a confused model must not block forever
    # A cautious model can flag the trusted template's own words (or a fact, word for word).
    known = _comparable("\n".join([reference, *facts.values()])).casefold()
    claims = (u.strip() for u in out.unsupported if u and u.strip())
    return [c for c in claims if _comparable(c).strip(" .\"'").casefold() not in known]


def fact_check(
    draft: str,
    facts: dict[str, str],
    reference: str = "",
    llm: LLM | None = None,
    use_model: bool = True,
    keep_values: bool = False,
) -> FactCheckResult:
    """`keep_values`: also fail a model's rewrite that lost a value of the template (never set for
    the user's own edit: they may cut what they like)."""
    result = FactCheckResult(
        code_issues=code_check(draft, facts, reference), tone_issues=tone_flags(draft)
    )
    if keep_values:
        result.omissions = dropped_values(draft, reference)
    if use_model and result.ok:
        result.model_issues = model_check(draft, facts, llm, reference)
    return result
