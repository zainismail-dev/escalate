"""Golden-set evals (section 11).

    uv run python -m evals.run --suite all                 # the model in .env; writes report.md
    uv run python -m evals.run --suite extraction
    uv run python -m evals.run --suite all --llm oracle    # offline harness check

Suites: extraction, classification, drafting (unsupported facts + tone flags), replies.
`oracle` answers with the expected values, so it proves the harness works without a model; its
scores are not quality scores.
"""

import argparse
import json
import re
import sys
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from escalate.agent.classify import classify_text
from escalate.agent.draft import draft_step, template_text
from escalate.agent.fact_check import code_check, model_check
from escalate.agent.intake import extract
from escalate.agent.judge_reply import judge
from escalate.agent.tone import tone_flags
from escalate.config import get_settings
from escalate.db import session as db_session
from escalate.db.models import Base, Case, CaseFact
from escalate.llm import LLM, LLMClient
from escalate.llm.client import Slot
from escalate.playbooks.resolver import resolve

HERE = Path(__file__).parent
CASES_DIR = HERE / "cases"
REPLIES = HERE / "replies.json"
REPORT = HERE / "report.md"
# Free-text fields pass when every word of the expected value appears in the answer.
FREE_TEXT = {"defect_description", "remedy_wanted", "scam_description", "last_promise_text"}
TARGETS = {
    "extraction": ("≥ 95%", lambda v: v >= 95),
    "classification": ("≥ 95%", lambda v: v >= 95),
    "unsupported": ("0", lambda v: v == 0),
    "tone": ("0", lambda v: v == 0),
    "replies": ("≥ 90%", lambda v: v >= 90),
}
# Values used to complete a draft's required facts when a golden case doesn't state them.
DRAFT_DEFAULTS = {
    "seller_contact": "support@seller.example",
    "company_contact": "support@company.example",
    "order_date": "2026-01-15",
    "order_id": "ORD-1001",
    "account_id": "ACC-1001",
    "cancel_requested_on": "2026-01-15",
    "amount": "100",
    "defect_description": "The item stopped working within a week.",
    "remedy_wanted": "a full refund",
    "paid_on": "2026-01-15",
    "payment_method": "bank transfer",
    "scam_description": "I paid for goods that were never delivered and the seller disappeared.",
    "bank_name": "My Bank",
    "bank_contact": "fraud@bank.example",
    "seller_name": "the seller",
    "company_name": "the company",
}
COUNTRY_CURRENCY = {
    "PK": "PKR",
    "IN": "INR",
    "GB": "GBP",
    "US": "USD",
    "DE": "EUR",
    "ES": "EUR",
    "FR": "EUR",
    "BR": "BRL",
    "NG": "NGN",
    "KE": "KES",
    "AE": "AED",
    "CA": "CAD",
}


def load_cases() -> list[dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(CASES_DIR.glob("*.json"))]


def load_replies() -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads(REPLIES.read_text(encoding="utf-8"))
    return data


def norm(value: str) -> str:
    v = unicodedata.normalize("NFKC", str(value)).strip().lower()
    v = re.sub(r"\s+", " ", v)
    if re.fullmatch(r"[\d,]+(\.\d+)?", v):
        v = v.replace(",", "")
        if "." in v:
            v = v.rstrip("0").rstrip(".")
    return v


def field_ok(key: str, expected: str, actual: str | None) -> bool:
    if actual is None:
        return False
    if key in FREE_TEXT:
        words = set(re.findall(r"\w+", norm(expected)))
        return words <= set(re.findall(r"\w+", norm(actual)))
    return norm(expected) == norm(actual)


@dataclass
class Score:
    hits: int = 0
    total: int = 0
    misses: list[str] = field(default_factory=list)

    @property
    def pct(self) -> float:
        return 100.0 * self.hits / self.total if self.total else 0.0


@dataclass
class DraftScore:
    drafts: int = 0
    unsupported: int = 0
    tone: int = 0
    misses: list[str] = field(default_factory=list)


# --- oracle (offline harness check) ---------------------------------------------------


def oracle(cases: list[dict[str, Any]], replies: list[dict[str, Any]]) -> LLM:
    from tests.fakes.fake_llm import FakeLLM

    by_text = {c["user_text"].strip(): c for c in cases}
    by_reply = {r["reply_text"].strip(): r for r in replies}

    def find_case(prompt: str) -> dict[str, Any]:
        return next(c for t, c in by_text.items() if t in prompt)

    def handler(prompt: str, _slot: Slot) -> dict[str, Any]:
        if prompt.startswith("You extract facts"):
            facts = find_case(prompt)["expected_facts"]
            return {"facts": {k: {"value": v, "confidence": 0.95} for k, v in facts.items()}}
        if prompt.startswith("Classify this complaint"):
            c = find_case(prompt)
            return {
                "case_type": c["case_type"],
                "country": c["country"],
                "region": c["region"],
                "language": c["language"],
                "urgent": c["urgent"],
                "reason": "oracle",
            }
        if prompt.startswith("You write the"):
            from tests.agent_env import echo_template

            return echo_template(prompt, _slot)
        if prompt.startswith("List every factual claim"):
            return {"unsupported": []}
        if prompt.startswith("A company replied"):
            reply = prompt.split("THE REPLY:", 1)[1].split("\n", 1)[0].strip()
            r = by_reply[reply]
            return {
                "verdict": r["expected"],
                "promise": None,
                "promise_date": None,
                "reason": "oracle",
            }
        raise AssertionError("unknown prompt")

    return FakeLLM(handler=handler)


# --- suites ---------------------------------------------------------------------------


def _fresh_db() -> None:
    engine = db_session.configure("sqlite://")
    Base.metadata.create_all(engine)


def run_extraction(cases: list[dict[str, Any]], llm: LLM) -> Score:
    score = Score()
    _fresh_db()
    with db_session.session_scope() as s:
        for gc in cases:
            pb = resolve(gc["country"], gc.get("region"), gc["case_type"])
            case = Case(description=gc["user_text"], country=gc["country"])
            s.add(case)
            s.flush()
            evidence = [(e["id"], e["text"]) for e in gc.get("evidence", [])]
            try:
                got = extract(
                    s,
                    case,
                    gc["user_text"],
                    evidence,
                    pb.required_facts,
                    pb.optional_facts,
                    llm=llm,
                ).facts
            except Exception as exc:  # a model failure counts as all-wrong for this case
                print(f"  {gc['id']}: extraction failed: {exc}", file=sys.stderr)
                got = {}
            for key, expected in gc["expected_facts"].items():
                score.total += 1
                if field_ok(key, expected, got.get(key)):
                    score.hits += 1
                else:
                    score.misses.append(f"{gc['id']}.{key}: want {expected!r} got {got.get(key)!r}")
    return score


def run_classification(cases: list[dict[str, Any]], llm: LLM) -> tuple[Score, Score]:
    """(case type + country + region, case type only)."""
    full, type_only = Score(), Score()
    for gc in cases:
        full.total += 1
        type_only.total += 1
        try:
            r = classify_text(gc["user_text"], llm)
        except Exception as exc:
            full.misses.append(f"{gc['id']}: failed: {exc}")
            continue
        type_ok = r.case_type == gc["case_type"]
        region_ok = gc.get("region") is None or r.region == gc["region"]
        country_ok = r.country == gc["country"]
        type_only.hits += type_ok
        if type_ok and region_ok and country_ok:
            full.hits += 1
        else:
            full.misses.append(
                f"{gc['id']}: want {gc['case_type']}/{gc['country']}/{gc.get('region')} "
                f"got {r.case_type}/{r.country}/{r.region}"
            )
    return full, type_only


def draft_facts(gc: dict[str, Any], required: list[str]) -> dict[str, str]:
    facts = dict(gc["expected_facts"])
    facts.setdefault("currency", COUNTRY_CURRENCY.get(gc["country"], "USD"))
    for key in required:
        facts.setdefault(key, DRAFT_DEFAULTS.get(key, f"({key})"))
    return facts


def run_drafting(cases: list[dict[str, Any]], llm: LLM, model_check_on: bool) -> DraftScore:
    score = DraftScore()
    _fresh_db()
    with db_session.session_scope() as s:
        for gc in cases:
            pb = resolve(gc["country"], gc.get("region"), gc["case_type"])
            step = pb.steps[0]
            facts = draft_facts(gc, [*pb.required_facts, *step.requires])
            case = Case(
                description=gc["user_text"],
                country=gc["country"],
                language=gc["language"],
                case_type=gc["case_type"],
                playbook_id=pb.id,
            )
            s.add(case)
            s.flush()
            for k, v in facts.items():
                s.add(CaseFact(case_id=case.id, key=k, value=v))
            s.flush()
            s.refresh(case)
            try:
                msg = draft_step(s, case, pb, step, llm=llm)
            except Exception as exc:
                score.misses.append(f"{gc['id']}: draft failed: {exc}")
                continue
            score.drafts += 1
            text = f"{msg.subject or ''}\n{msg.body}"
            issues = code_check(text, facts, template_text(case, pb, step))
            if model_check_on and not issues:
                issues = model_check(text, facts, llm)
            flags = tone_flags(msg.body)
            score.unsupported += len(issues)
            score.tone += len(flags)
            for i in issues:
                score.misses.append(f"{gc['id']}: unsupported: {i}")
            for f in flags:
                score.misses.append(f"{gc['id']}: tone: {f}")
    return score


def run_replies(replies: list[dict[str, Any]], llm: LLM) -> Score:
    score = Score()
    for r in replies:
        score.total += 1
        try:
            got = judge(r["reply_text"], r["remedy_wanted"], llm).verdict
        except Exception as exc:
            score.misses.append(f"{r['id']}: failed: {exc}")
            continue
        if got == r["expected"]:
            score.hits += 1
        else:
            score.misses.append(
                f"{r['id']}: want {r['expected']} got {got}: {r['reply_text'][:60]}"
            )
    return score


# --- report ----------------------------------------------------------------------------


def _row(name: str, key: str, value: float, shown: str) -> str:
    target, ok = TARGETS[key]
    return f"| {name} | {shown} | {target} | {'✅' if ok(value) else '❌'} |"


def write_report(results: dict[str, Any], mode: str, path: Path = REPORT) -> str:
    s = get_settings()
    model = (
        "oracle (expected answers)"
        if mode == "oracle"
        else (
            f"smart={s.model_smart or '?'} fast={s.model_fast_or_smart or '?'} at {s.llm_base_url}"
        )
    )
    cases, replies = results["n_cases"], results["n_replies"]
    lines = [
        "# Eval report",
        "",
        f"- Run: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')} UTC",
        f"- Model: {model}",
        f"- Golden set: {cases} cases, {replies} sample replies",
    ]
    if mode == "oracle":
        lines.append("- **Oracle run:** checks the harness only; not a quality score.")
    lines += ["", "| Eval | Result | Target | Pass |", "| --- | --- | --- | --- |"]
    if "extraction" in results:
        e = results["extraction"]
        lines.append(
            _row(
                "Fact extraction field accuracy",
                "extraction",
                e.pct,
                f"{e.pct:.1f}% ({e.hits}/{e.total})",
            )
        )
    if "classification" in results:
        c, t = results["classification"]
        lines.append(
            _row(
                "Case type + country + region",
                "classification",
                c.pct,
                f"{c.pct:.1f}% ({c.hits}/{c.total}); type only {t.pct:.1f}%",
            )
        )
    if "drafting" in results:
        d = results["drafting"]
        lines.append(
            _row(
                "Unsupported facts in drafts",
                "unsupported",
                d.unsupported,
                f"{d.unsupported} in {d.drafts} drafts",
            )
        )
        lines.append(
            _row(
                "Drafts flagged for threats or rudeness",
                "tone",
                d.tone,
                f"{d.tone} flags in {d.drafts} drafts",
            )
        )
    if "replies" in results:
        r = results["replies"]
        lines.append(
            _row("Reply verdict correct", "replies", r.pct, f"{r.pct:.1f}% ({r.hits}/{r.total})")
        )
    for key, title in [
        ("extraction", "Extraction misses"),
        ("classification", "Classification misses"),
        ("drafting", "Drafting issues"),
        ("replies", "Reply-judge misses"),
    ]:
        if key not in results:
            continue
        res = results[key][0] if key == "classification" else results[key]
        if res.misses:
            lines += ["", f"## {title}", ""] + [f"- {m}" for m in res.misses[:40]]
    text = "\n".join(lines) + "\n"
    history = _history(path)
    path.write_text(text + history, encoding="utf-8")
    return text


HISTORY = "## History"


def _history(path: Path) -> str:
    """Keep the hand-written before/after log at the end of the report across runs."""
    if not path.is_file():
        return ""
    old = path.read_text(encoding="utf-8")
    return "\n" + old[old.index(HISTORY) :] if HISTORY in old else ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument(
        "--suite",
        default="all",
        choices=["extraction", "classification", "drafting", "replies", "all"],
    )
    ap.add_argument("--llm", default="real", choices=["real", "oracle"])
    ap.add_argument("--report", default=str(REPORT), help="where to write the Markdown report")
    args = ap.parse_args(argv)

    cases, replies = load_cases(), load_replies()
    llm: LLM = oracle(cases, replies) if args.llm == "oracle" else LLMClient()
    suites = (
        ["extraction", "classification", "drafting", "replies"]
        if args.suite == "all"
        else [args.suite]
    )
    results: dict[str, Any] = {"n_cases": len(cases), "n_replies": len(replies)}
    runners: dict[str, Callable[[], Any]] = {
        "extraction": lambda: run_extraction(cases, llm),
        "classification": lambda: run_classification(cases, llm),
        "drafting": lambda: run_drafting(cases, llm, model_check_on=True),
        "replies": lambda: run_replies(replies, llm),
    }
    for name in suites:
        results[name] = runners[name]()
    print(write_report(results, args.llm, Path(args.report)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
