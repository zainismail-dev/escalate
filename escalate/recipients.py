"""Look-alike recipients: an address with non-ASCII characters (e.g. Cyrillic "а" in
"pаypal.com") can be planted in evidence to send letters to someone else. The user sees a
warning and the punycode form (what mail servers actually use) before approving."""

import unicodedata
from dataclasses import dataclass


@dataclass
class Lookalike:
    warn: bool
    ascii_form: str | None  # the domain in punycode (xn--…); None if it can't be encoded
    scripts: list[str]  # letter scripts seen, e.g. ["CYRILLIC", "LATIN"]


def _script(ch: str) -> str | None:
    if not ch.isalpha():
        return None
    try:
        return unicodedata.name(ch).split()[0]
    except ValueError:
        return "UNKNOWN"


def check_lookalike(address: str | None) -> Lookalike:
    if not address or address.isascii():
        return Lookalike(False, None, ["LATIN"] if address else [])
    scripts = sorted({s for s in map(_script, address) if s})
    local, _, domain = address.rpartition("@")
    try:
        puny = domain.encode("idna").decode("ascii") if domain else ""
        ascii_form = f"{local}@{puny}" if local else puny
    except UnicodeError:
        ascii_form = None
    return Lookalike(True, ascii_form, scripts)
