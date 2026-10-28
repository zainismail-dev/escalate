"""UI strings from locales/<lang>.json. Missing keys fall back to English, then to the key."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

LOCALES = Path(__file__).resolve().parents[1] / "locales"
RTL = {"ur", "ar", "fa", "he"}


@lru_cache
def strings(lang: str) -> dict[str, str]:
    path = LOCALES / f"{lang}.json"
    if not path.is_file():
        return {}
    data: dict[str, str] = json.loads(path.read_text(encoding="utf-8"))
    return data


def available() -> list[str]:
    return sorted(p.stem for p in LOCALES.glob("*.json"))


def translate(lang: str, key: str, **values: Any) -> str:
    text = strings(lang).get(key) or strings("en").get(key) or key
    return text.format(**values) if values else text
