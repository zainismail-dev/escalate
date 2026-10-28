"""Golden-set evals.

    uv run python -m evals.run --suite extraction            # against the model in .env
    uv run python -m evals.run --suite extraction --llm oracle  # offline harness check

`oracle` answers with the expected values, so it always scores 100%: it proves the harness
works without a model. Real scores need a real model.
"""

import argparse
import json
import re
import sys
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from escalate.agent.intake import extract
from escalate.db import session as db_session
from escalate.db.models import Base, Case
from escalate.llm import LLM, LLMClient
from escalate.playbooks.resolver import resolve

CASES_DIR = Path(__file__).parent / "cases"
# Free-text fields pass when every word of the expected value appears in the answer.
FREE_TEXT = {"defect_description", "remedy_wanted", "scam_description", "last_promise_text"}


def load_cases() -> list[dict[str, Any]]:
    return [json.loads(p.read_text()) for p in sorted(CASES_DIR.glob("*.json"))]


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


def oracle_extraction(case: dict[str, Any]) -> LLM:
    from tests.fakes.fake_llm import FakeLLM

    facts = {k: {"value": v, "confidence": 0.95} for k, v in case["expected_facts"].items()}
    return FakeLLM(handler=lambda _p, _s: {"facts": facts, "missing": []})


def run_extraction(cases: list[dict[str, Any]], make_llm: Callable[[dict[str, Any]], LLM]) -> Score:
    score = Score()
    engine = db_session.configure("sqlite://")
    Base.metadata.create_all(engine)
    with db_session.session_scope() as s:
        for gc in cases:
            pb = resolve(gc["country"], gc.get("region"), gc["case_type"])
            case = Case(description=gc["user_text"], country=gc["country"])
            s.add(case)
            s.flush()
            evidence = [(e["id"], e["text"]) for e in gc.get("evidence", [])]
            try:
                result = extract(
                    s,
                    case,
                    gc["user_text"],
                    evidence,
                    pb.required_facts,
                    pb.optional_facts,
                    llm=make_llm(gc),
                )
                got = result.facts
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--suite", default="all", choices=["extraction", "all"])
    ap.add_argument("--llm", default="real", choices=["real", "oracle"])
    args = ap.parse_args(argv)

    cases = load_cases()
    if args.llm == "oracle":
        make_llm: Callable[[dict[str, Any]], LLM] = oracle_extraction
    else:
        client = LLMClient()
        make_llm = lambda _c: client  # noqa: E731

    score = run_extraction(cases, make_llm)
    print(f"extraction: {score.pct:.1f}% ({score.hits}/{score.total} fields, {len(cases)} cases)")
    for m in score.misses:
        print(f"  miss {m}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
