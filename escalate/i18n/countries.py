"""Every country (ISO 3166-1, from CLDR via Babel), its currency (ISO 4217) and which case types
have a local playbook. Countries without one use the generic international ladder."""

import re
from functools import lru_cache
from pathlib import Path

from babel import Locale
from babel.numbers import get_territory_currencies
from pydantic import BaseModel

from escalate.config import get_settings
from escalate.playbooks.loader import load_all

# CLDR territories that are not ISO 3166-1 countries (groupings, reserved and private codes).
_NOT_COUNTRIES = frozenset(
    ["AC", "CP", "CQ", "DG", "EA", "EU", "EZ", "IC", "QO", "TA", "UN", "XA", "XB", "ZZ"]
)
_LANG_TAG = re.compile(r"^[a-z]{2,3}(-[A-Z]{2})?$")
RTL_LANGUAGES = frozenset({"ar", "fa", "he", "ur", "ps", "sd", "ug", "yi", "dv", "ckb"})


class CountryOut(BaseModel):
    code: str
    currency: str | None
    local_pack: bool  # a country playbook exists for at least one case type
    packs: dict[str, str]  # case_type -> playbook id (local packs only)
    regions: list[str]  # ISO 3166-2 codes some local playbook covers


@lru_cache
def country_codes() -> tuple[str, ...]:
    codes = [str(c) for c in Locale("en").territories]
    keep = (c for c in codes if len(c) == 2 and c.isalpha() and c not in _NOT_COUNTRIES)
    return tuple(sorted(keep))


def currency_for(country: str | None) -> str | None:
    """The country's current legal tender, e.g. PK -> PKR. None when unknown."""
    if not country:
        return None
    found = get_territory_currencies(country.upper(), tender=True)
    return found[0] if found else None


def normalize_language(tag: str) -> str:
    """Accept BCP-47 tags like `ur`, `ur-PK`, `pt_BR`; return `ll` or `ll-RR`.

    Raises ValueError for anything else (scripts and variants are not supported yet).
    """
    parts = tag.strip().replace("_", "-").split("-")
    norm = parts[0].lower() + (f"-{parts[1].upper()}" if len(parts) > 1 else "")
    if len(parts) > 2 or not _LANG_TAG.match(norm):
        raise ValueError("language must be a BCP-47 tag such as en, ur or pt-BR")
    return norm


def letter_language(tag: str) -> str:
    """Normalize a letter language and check it is enabled (ENABLED_LETTER_LANGUAGES, by primary
    subtag: `en` also allows `en-GB`). Raises ValueError otherwise."""
    norm = normalize_language(tag)
    enabled = get_settings().enabled_letter_languages
    if primary_language(norm) not in {primary_language(e) for e in enabled}:
        raise ValueError(f"letter language {norm!r} is not enabled; enabled: {', '.join(enabled)}")
    return norm


def default_letter_language() -> str:
    """Settings' default letter language if it is enabled, else the first enabled one."""
    s = get_settings()
    try:
        return letter_language(s.default_language)
    except ValueError:
        return normalize_language(s.enabled_letter_languages[0])


def primary_language(tag: str | None) -> str:
    return (tag or "en").replace("_", "-").split("-")[0].lower()


def is_rtl(tag: str | None) -> bool:
    return primary_language(tag) in RTL_LANGUAGES


def coverage(root: Path | None = None) -> list[CountryOut]:
    packs: dict[str, dict[str, str]] = {}
    regions: dict[str, set[str]] = {}
    for pb in load_all(Path(root or get_settings().playbooks_dir)).values():
        if pb.generic or pb.country == "INTL":
            continue
        packs.setdefault(pb.country, {}).setdefault(pb.case_type, pb.id)
        regions.setdefault(pb.country, set()).update(pb.regions)
    return [
        CountryOut(
            code=c,
            currency=currency_for(c),
            local_pack=c in packs,
            packs=packs.get(c, {}),
            regions=sorted(regions.get(c, set())),
        )
        for c in country_codes()
    ]
