"""Pick the most specific playbook: company -> region -> country -> intl/generic."""

import re
from pathlib import Path

from escalate.playbooks.loader import PlaybookError, load_all
from escalate.playbooks.models import GENERIC_COUNTRY, Playbook


def company_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _rank(pb: Playbook, country: str, region: str | None, company: str | None) -> int | None:
    """Higher is more specific; None means the playbook does not apply."""
    in_country = pb.country == country
    if pb.company:
        if company is None or company_slug(company) != pb.company:
            return None
        if pb.country not in (country, GENERIC_COUNTRY):
            return None
        return 40 if in_country else 35
    if in_country:
        if pb.regions:
            if region is None:
                return 15  # region unknown: still better than generic, the UI asks for it
            return 30 if region in pb.regions else None
        return 20
    if pb.country == GENERIC_COUNTRY:
        return 10
    return None


def resolve(
    country: str | None,
    region: str | None,
    case_type: str,
    company: str | None = None,
    root: Path | None = None,
) -> Playbook:
    cc = (country or GENERIC_COUNTRY).upper()
    reg = region.upper() if region else None
    ranked: list[tuple[int, str, Playbook]] = []
    for pb in load_all(root).values():
        if pb.case_type != case_type:
            continue
        score = _rank(pb, cc, reg, company)
        if score is not None:
            ranked.append((score, pb.id, pb))
    if not ranked:
        raise PlaybookError(f"no playbook for case_type={case_type!r} (not even intl/generic)")
    ranked.sort(key=lambda t: (-t[0], t[1]))
    return ranked[0][2]
