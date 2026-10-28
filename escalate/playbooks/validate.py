"""Playbook validator CLI, run in CI.

    uv run python -m escalate.playbooks.validate playbooks/ [--templates templates/]

Fails on schema errors, missing templates, unknown step targets, unknown facts in templates
or `when`, duplicate ids and missing sources. Warns when `last_verified` is over 12 months old
or a source has no URL.
"""

import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from jinja2 import Environment, TemplateSyntaxError, meta

from escalate.playbooks.loader import PlaybookError, playbook_files, read_raw, schema_errors
from escalate.playbooks.models import Playbook, parse_when, template_languages
from escalate.templates_engine import make_env

STALE_AFTER = timedelta(days=365)
# CLAUDE.md rule 5: never ask users for passwords, PINs or one-time codes.
FORBIDDEN_FACT = re.compile(r"(password|passcode|(^|_)pin($|_)|otp|cvv|cvc|secret|one_time)", re.I)
# Variables every template may use besides the playbook's facts (see escalate/templates_engine).
TEMPLATE_CONTEXT = {"today", "reply_by", "language", "locale", "generic", "case_ref", "late"}


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def error(self, where: Path | str, msg: str) -> None:
        self.errors.append(f"ERROR {where}: {msg}")

    def warn(self, where: Path | str, msg: str) -> None:
        self.warnings.append(f"WARN  {where}: {msg}")


def _template_vars(env: Environment, path: Path) -> set[str]:
    ast = env.parse(path.read_text(encoding="utf-8"))
    return set(meta.find_undeclared_variables(ast))


def check_playbook(pb: Playbook, templates_dir: Path, report: Report, today: date) -> None:
    where = pb.path or pb.id
    step_ids = [s.id for s in pb.steps]
    facts = set(pb.all_facts)
    env = make_env()

    for fact in sorted(facts):
        if FORBIDDEN_FACT.search(fact):
            report.error(where, f"fact {fact!r} looks like a secret; never ask for it")
    if len(set(step_ids)) != len(step_ids):
        report.error(where, "duplicate step ids")
    if not pb.sources:
        report.error(where, "no sources: every playbook must cite at least one")
    for src in pb.sources:
        if not src.url and not pb.generic:
            report.warn(where, f"source {src.title!r} has no URL yet")
    if today - pb.last_verified > STALE_AFTER:
        report.warn(where, f"last_verified {pb.last_verified} is more than 12 months old")

    for step in pb.steps:
        for attr in ("on_no_reply", "on_refused", "on_partial"):
            target = getattr(step, attr)
            if target and target not in step_ids:
                report.error(where, f"step {step.id}: {attr} -> unknown step {target!r}")
        if step.when:
            parsed = parse_when(step.when)
            if parsed is None:
                report.error(where, f"step {step.id}: bad `when` {step.when!r}")
            elif parsed[0] not in facts:
                report.error(where, f"step {step.id}: `when` uses undeclared fact {parsed[0]!r}")
        for key in [*step.requires, step.recipient_fact]:
            if key and key not in facts:
                report.error(where, f"step {step.id}: undeclared fact {key!r}")
        for ref in filter(None, [step.template, step.adds_if_late]):
            langs = template_languages(templates_dir, ref)
            if not langs:
                report.error(where, f"step {step.id}: missing template {ref}")
                continue
            if "en" not in langs:  # English is the fallback for every other language
                report.error(where, f"step {step.id}: missing template {ref} (no en/ fallback)")
            pack, _, name = ref.partition("/")
            for lang in langs:
                tpl = templates_dir / pack / lang / name
                try:
                    unknown = _template_vars(env, tpl) - facts - TEMPLATE_CONTEXT
                except TemplateSyntaxError as exc:
                    report.error(tpl, f"template syntax error: {exc}")
                    continue
                if unknown:
                    report.error(tpl, f"uses values that are not playbook facts: {sorted(unknown)}")

    for dl in pb.deadlines:
        if dl.from_step and dl.from_step not in step_ids:
            report.error(where, f"deadline {dl.id}: from_step -> unknown step {dl.from_step!r}")
        if dl.from_fact and dl.from_fact not in facts:
            report.error(where, f"deadline {dl.id}: from_fact uses undeclared fact")


def check_checklists(root: Path, report: Report) -> None:
    """Scam checklists must load and keep the two safety warnings."""
    from pydantic import ValidationError

    from escalate.agent.checklist import Checklist

    for path in sorted(Path(root).rglob("scam_checklist.yaml")):
        try:
            cl = Checklist.model_validate(read_raw(path))
        except (PlaybookError, ValidationError) as exc:
            report.error(path, f"bad checklist: {exc}")
            continue
        text = " ".join(cl.warnings).lower()
        if "otp" not in text or "recovery" not in text:
            report.error(path, "checklist must warn about OTPs/passwords and recovery scammers")
        if not cl.items:
            report.error(path, "checklist has no items")


def validate(root: Path, templates_dir: Path, today: date | None = None) -> Report:
    report = Report()
    check_checklists(root, report)
    today = today or date.today()
    seen: dict[str, Path] = {}
    files = playbook_files(root)
    if not files:
        report.error(root, "no playbooks found")
    for path in files:
        try:
            data = read_raw(path)
        except (PlaybookError, ValueError) as exc:
            report.error(path, str(exc))
            continue
        errs = schema_errors(data)
        for e in errs:
            report.error(path, f"schema: {e}")
        if errs:
            continue
        pb = Playbook.model_validate(data)
        pb.path = path
        if pb.id in seen:
            report.error(path, f"duplicate id {pb.id!r} (also in {seen[pb.id]})")
        seen[pb.id] = path
        check_playbook(pb, templates_dir, report, today)
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root", nargs="?", default="playbooks", type=Path)
    ap.add_argument("--templates", default=None, type=Path)
    args = ap.parse_args(argv)
    templates = args.templates or args.root.resolve().parent / "templates"
    report = validate(args.root, templates)
    for line in [*report.warnings, *report.errors]:
        print(line, file=sys.stderr if line.startswith("ERROR") else sys.stdout)
    n = len(playbook_files(args.root))
    status = "FAILED" if report.errors else "OK"
    errs, warns = len(report.errors), len(report.warnings)
    print(f"{status}: {n} playbook(s), {errs} error(s), {warns} warning(s)")
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
