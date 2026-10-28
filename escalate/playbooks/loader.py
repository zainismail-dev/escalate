"""Read playbook YAML files, validate them against the JSON Schema, and cache them by id."""

import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from escalate.config import get_settings
from escalate.playbooks.models import Playbook

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "playbook.schema.json"


class PlaybookError(Exception):
    pass


@lru_cache
def _validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(SCHEMA_PATH.read_text()))


def _jsonable(data: Any) -> Any:
    """YAML turns 2026-10-28 into a date; the schema expects strings."""
    if isinstance(data, dict):
        return {k: _jsonable(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_jsonable(v) for v in data]
    if isinstance(data, date):
        return data.isoformat()
    return data


def read_raw(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise PlaybookError(f"{path}: not a YAML mapping")
    return _jsonable(data)


def schema_errors(data: dict[str, Any]) -> list[str]:
    errors = sorted(_validator().iter_errors(data), key=lambda e: list(e.path))
    return [f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors]


def playbook_files(root: Path) -> list[Path]:
    # scam_checklist.yaml files are checklists, not ladders (task 3.2)
    return sorted(p for p in Path(root).rglob("*.yaml") if not p.name.endswith("checklist.yaml"))


def load_file(path: Path) -> Playbook:
    data = read_raw(path)
    errs = schema_errors(data)
    if errs:
        raise PlaybookError(f"{path}: " + "; ".join(errs))
    pb = Playbook.model_validate(data)
    pb.path = path
    return pb


def load_all(root: Path | None = None) -> dict[str, Playbook]:
    return dict(_load_all_cached(Path(root or get_settings().playbooks_dir).resolve()))


@lru_cache
def _load_all_cached(root: Path) -> tuple[tuple[str, Playbook], ...]:
    books: dict[str, Playbook] = {}
    for path in playbook_files(root):
        pb = load_file(path)
        if pb.id in books:
            raise PlaybookError(f"duplicate playbook id {pb.id!r} in {path}")
        books[pb.id] = pb
    return tuple(books.items())


def get_playbook(playbook_id: str, root: Path | None = None) -> Playbook:
    try:
        return load_all(root)[playbook_id]
    except KeyError:
        raise PlaybookError(f"unknown playbook {playbook_id!r}") from None


def clear_cache() -> None:
    _load_all_cached.cache_clear()
