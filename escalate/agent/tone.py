"""Code-side tone check: flag threats, insults and shouting in a draft.

Letters must be firm, polite and factual. Stating a lawful next step ("I will file a complaint")
is fine; threats of harm, insults and abuse are not.
"""

import re

_PHRASES = [
    # insults / abuse
    r"\bidiots?\b",
    r"\bstupid\b",
    r"\bmorons?\b",
    r"\bliars?\b",
    r"\bcrooks?\b",
    r"\bthie(f|ves)\b",
    r"\bscumbags?\b",
    r"\bincompetent\b",
    r"\bpathetic\b",
    r"\bdisgusting\b",
    r"\bshameless\b",
    r"\bfraudsters?\b(?! (who|that) (contacted|called))",
    # threats beyond the lawful next step
    r"\byou will regret\b",
    r"\bor else\b",
    r"\bdestroy (you|your)\b",
    r"\bruin (you|your)\b",
    r"\bexpose you\b",
    r"\bshame you\b",
    r"\bgo viral\b",
    r"\bhurt\b",
    r"\bpunish\b",
    r"\bnamed and shamed\b",
    r"\bwatch your back\b",
    # other languages (a few common ones)
    r"\bidiota[s]?\b",
    r"\bestafadores?\b",
    r"\bescrocs?\b",
    r"\bbetrüger\b",
    r"\bladrões\b",
]
_RX = re.compile("|".join(_PHRASES), re.IGNORECASE)
# Upper-case headings that templates use on purpose.
_ALLOWED_CAPS = {
    "LEGAL NOTICE",
    "LETTER BEFORE ACTION",
    "COMPLAINT",
    "PRAYER",
    "BEFORE THE",
    "APPLICATION FOR CONDONATION OF DELAY",
    "DISTRICT CONSUMER COURT",
    "DISTRICT CONSUMER DISPUTES REDRESSAL COMMISSION",
    "COMPLAINT UNDER THE CONSUMER PROTECTION ACT",
}
_SHOUT = re.compile(r"\b(?:[A-Z]{3,}[\s,!]+){3,}[A-Z]{3,}\b")


def tone_flags(text: str) -> list[str]:
    flags = [f"wording: {m.group(0)!r}" for m in _RX.finditer(text)]
    if re.search(r"[!?]{2,}", text):
        flags.append("repeated !/? marks")
    for line in text.splitlines():
        stripped = line.strip()
        if any(stripped.startswith(h) for h in _ALLOWED_CAPS):
            continue
        m = _SHOUT.search(stripped)
        if m:
            flags.append(f"shouting: {m.group(0)[:40]!r}")
    return flags
