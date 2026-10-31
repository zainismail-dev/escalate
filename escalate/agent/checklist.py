"""Time-critical scam steps shown before any letter: playbooks/<cc>/scam_checklist.yaml."""

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from escalate.config import get_settings


class ChecklistItem(BaseModel):
    id: str
    title: str
    detail: str = ""
    urgent: bool = True


class Checklist(BaseModel):
    country: str
    items: list[ChecklistItem]
    warnings: list[str] = Field(default_factory=list)
    sources: list[dict[str, str]] = Field(default_factory=list)


class UnsafeChecklistPath(ValueError):
    """A checklist file that resolves outside the playbooks folder (e.g. a symlinked pack)."""


def _country_dirs(base: Path) -> dict[str, Path]:
    """The country packs on disk: playbooks/<cc>/ folders named by an ISO 3166-1 alpha-2 code."""
    if not base.is_dir():
        return {}
    return {d.name: d for d in base.iterdir() if re.fullmatch(r"[a-z]{2}", d.name) and d.is_dir()}


def checklist_path(country: str | None, root: Path | None = None) -> Path:
    """The country's checklist, else the generic one. The folder comes from the packs on disk,
    looked up by the code, so the user's text never becomes part of a path."""
    base = Path(root or get_settings().playbooks_dir)
    p = base / "intl" / "generic" / "scam_checklist.yaml"
    if country and re.fullmatch(r"[A-Za-z]{2}", country):
        folder = _country_dirs(base).get(country.lower())
        if folder is not None and (folder / "scam_checklist.yaml").is_file():
            p = folder / "scam_checklist.yaml"
    if not p.resolve().is_relative_to(base.resolve()):
        raise UnsafeChecklistPath(f"{p} is outside {base}")
    return p


def load_checklist(country: str | None, root: Path | None = None) -> Checklist:
    data = yaml.safe_load(checklist_path(country, root).read_text(encoding="utf-8"))
    return Checklist.model_validate(data)
