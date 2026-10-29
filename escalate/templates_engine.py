"""Render letter templates with Jinja2 StrictUndefined: a missing placeholder blocks the draft."""

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from jinja2 import FileSystemLoader, StrictUndefined, UndefinedError, pass_context
from jinja2.runtime import Context
from jinja2.sandbox import SandboxedEnvironment

from escalate.config import get_settings
from escalate.db.models import utcnow
from escalate.i18n.formatting import format_date, format_money, locale_for
from escalate.playbooks.models import Playbook, Step, template_file


class MissingPlaceholder(Exception):
    """A template needs a value that is not in the case facts."""

    def __init__(self, template: str, detail: str) -> None:
        super().__init__(f"{template}: {detail}")
        self.template = template
        self.detail = detail


@pass_context
def _money(ctx: Context, amount: object, currency: str | None) -> str:
    return format_money(amount, currency, ctx.get("locale") or ctx.get("language", "en"))


@pass_context
def _date(ctx: Context, value: Any) -> str:
    return format_date(value, ctx.get("locale") or ctx.get("language", "en"))


def make_env(templates_dir: Path | None = None) -> SandboxedEnvironment:
    """Templates are repo files; case facts are only ever passed in as variables, never compiled
    as template source, so `{{ 7*7 }}` in a fact stays literal text. The sandbox also blocks
    attribute tricks (`__class__`, `__globals__`) should a contributed template try them."""
    env = SandboxedEnvironment(
        loader=FileSystemLoader(str(templates_dir)) if templates_dir else None,
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=False,
        # Markdown letters, never HTML: escaping would put "&amp;" in a posted letter. They are
        # HTML-escaped when turned into a PDF (export/pdf.py text_to_html).
        autoescape=False,
    )
    env.filters["money"] = _money
    env.filters["date"] = _date
    return env


def render_file(path: Path, context: dict[str, Any]) -> str:
    env = make_env(path.parent)
    try:
        return env.get_template(path.name).render(**context)
    except UndefinedError as exc:
        raise MissingPlaceholder(str(path), str(exc)) from exc


class MissingFacts(Exception):
    """Drafting is blocked until the user supplies these facts."""

    def __init__(self, keys: list[str]) -> None:
        super().__init__(f"missing facts: {', '.join(keys)}")
        self.keys = keys


@dataclass
class Rendered:
    subject: str
    body: str


def split_subject(text: str) -> Rendered:
    """A template's first line may be `Subject: ...`."""
    lines = text.lstrip("\n").split("\n")
    if lines and lines[0].lower().startswith("subject:"):
        return Rendered(lines[0].split(":", 1)[1].strip(), "\n".join(lines[1:]).strip() + "\n")
    return Rendered("", text.strip() + "\n")


def missing_for_step(pb: Playbook, step: Step, facts: dict[str, str]) -> list[str]:
    needed = [*pb.required_facts, *step.requires]
    return [k for k in dict.fromkeys(needed) if not str(facts.get(k) or "").strip()]


def step_context(
    pb: Playbook,
    step: Step,
    facts: dict[str, str],
    language: str,
    today: date | None = None,
    late: bool = False,
    country: str | None = None,
) -> dict[str, Any]:
    today = today or utcnow().date()
    locale = locale_for(language, country)
    ctx: dict[str, Any] = dict.fromkeys(pb.optional_facts)
    ctx.update({k: v for k, v in facts.items() if k in pb.all_facts and str(v).strip()})
    reply_by = today + timedelta(days=step.wait_days or 0)
    ctx.update(
        today=format_date(today, locale),
        reply_by=format_date(reply_by, locale),
        language=primary(language),
        tag=language,
        locale=locale,
        generic=pb.generic,
        late=late,
    )
    return ctx


def render_ref(ref: str, ctx: dict[str, Any], templates_dir: Path | None = None) -> str:
    tdir = Path(templates_dir or get_settings().templates_dir)
    path = template_file(tdir, ref, str(ctx.get("tag") or ctx.get("language", "en")))
    if path is None:
        raise FileNotFoundError(f"template {ref} not found under {tdir}")
    return render_file(path, ctx)


def primary(language: str) -> str:
    """BCP-47 `ur-PK` -> `ur`: templates branch on the primary language only."""
    return language.replace("_", "-").split("-")[0].lower()


def disclaimer(language: str, generic: bool, templates_dir: Path | None = None) -> str:
    tdir = Path(templates_dir or get_settings().templates_dir)
    return render_file(
        tdir / "_shared" / "disclaimer.md.j2", {"language": primary(language), "generic": generic}
    ).strip()


def render_step(
    pb: Playbook,
    step: Step,
    facts: dict[str, str],
    language: str,
    today: date | None = None,
    late: bool = False,
    templates_dir: Path | None = None,
    country: str | None = None,
) -> Rendered:
    """Fill a step's template with case facts only. Raises MissingFacts / MissingPlaceholder."""
    missing = missing_for_step(pb, step, facts)
    if missing:
        raise MissingFacts(missing)
    ctx = step_context(pb, step, facts, language, today, late, country)
    out = split_subject(render_ref(step.template, ctx, templates_dir))
    if late and step.adds_if_late:
        extra = split_subject(render_ref(step.adds_if_late, ctx, templates_dir))
        title = extra.subject.upper() if extra.subject else ""
        out.body = f"{out.body.rstrip()}\n\n---\n\n{title}\n\n{extra.body}".replace(
            "\n\n\n", "\n\n"
        )
    return out
