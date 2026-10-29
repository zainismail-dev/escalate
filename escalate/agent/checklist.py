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


def checklist_path(country: str | None, root: Path | None = None) -> Path:
    base = Path(root or get_settings().playbooks_dir)
    if country and re.fullmatch(r"[A-Za-z]{2}", country):  # ISO 3166-1 alpha-2, never a path
        p = base / country.lower() / "scam_checklist.yaml"
        if p.is_file():
            return p
    return base / "intl" / "generic" / "scam_checklist.yaml"


def load_checklist(country: str | None, root: Path | None = None) -> Checklist:
    data = yaml.safe_load(checklist_path(country, root).read_text(encoding="utf-8"))
    return Checklist.model_validate(data)
