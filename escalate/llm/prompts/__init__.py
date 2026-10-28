"""Versioned prompt files. `{name}` placeholders are filled; other braces (JSON) are left alone."""

from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent


@lru_cache
def _raw(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8")


def render_prompt(name: str, **values: object) -> str:
    text = _raw(name)
    for key, value in values.items():
        text = text.replace("{" + key + "}", str(value))
    return text
