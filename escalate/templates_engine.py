"""Render letter templates with Jinja2 StrictUndefined: a missing placeholder blocks the draft."""

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, UndefinedError, pass_context
from jinja2.runtime import Context

from escalate.i18n.formatting import format_date, format_money


class MissingPlaceholder(Exception):
    """A template needs a value that is not in the case facts."""

    def __init__(self, template: str, detail: str) -> None:
        super().__init__(f"{template}: {detail}")
        self.template = template
        self.detail = detail


@pass_context
def _money(ctx: Context, amount: object, currency: str | None) -> str:
    return format_money(amount, currency, ctx.get("language", "en"))


@pass_context
def _date(ctx: Context, value: Any) -> str:
    return format_date(value, ctx.get("language", "en"))


def make_env(templates_dir: Path | None = None) -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)) if templates_dir else None,
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=False,
        autoescape=False,  # Markdown letters, never HTML
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
