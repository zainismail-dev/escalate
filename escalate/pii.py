"""Mask secrets and identity numbers before they are logged, stored as case text or drafted.

CLAUDE.md rule 5: never log full card numbers, IBANs, national IDs, passwords or OTPs.
Masks keep the last 4 characters so the user can still recognise the item.
"""

import logging
import re

MASK = "•"

_CARD = re.compile(r"(?<![\w-])(?:\d[ -]?){12,18}\d(?![\w-])")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}(?:[ ]?[A-Z0-9]{1,4})?\b")
_NATIONAL_IDS = [
    re.compile(r"\b\d{5}-\d{7}-\d\b"),  # Pakistan CNIC
    # India Aadhaar: exactly 12 digits, not part of a longer digit run
    re.compile(r"(?<![\d-])(?<!\d )\d{4}[ -]\d{4}[ -]\d{4}(?![ -]?\d)"),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # US SSN
    re.compile(r"\b[A-CEGHJ-PR-TW-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b"),  # UK NI number
]
# Separators: each run of spaces follows a token, never another optional run of spaces, so a
# long run of whitespace can't be split between several `\s*` (polynomial backtracking).
_SECRET = re.compile(
    r"(?i)(?<!\w)(password|passcode|passwd|pin|otp|one[- ]time (?:code|password)|cvv|cvc"
    r"|mot de passe|contraseña|senha|passwort)(?!\w)"
    r"(\s*(?:[:=#-]\s*)?(?:(?:is|was|code|est|es|é|ist)(?!\w)\s*)?(?:[:=#-]\s*)?)(\S+)"
)
# Short forms are ordinary words ("pass the exam"): only with an explicit ":" or "=".
_SHORT_SECRET = re.compile(r"(?i)\b(pw|pwd|pass)(\s*[:=]\s*)(\S+)")
# UK bank details: "sort code 12-34-56", "account (number|no) 12345678".
_SORT_CODE = re.compile(r"(?i)\b(sort[- ]?code)(\s*(?:[:#]\s*)?)(\d{2}[- ]?\d{2}[- ]?\d{2})\b")
_UK_ACCOUNT = re.compile(r"(?i)\b(account(?:\s+(?:number|no\.?|num))?)(\s*(?:[:#]\s*)?)(\d{8})\b")


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def _keep_last4(raw: str) -> str:
    chars = re.sub(r"[\s-]", "", raw)
    return MASK * 4 + " " + chars[-4:]


def _card(m: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", m.group(0))
    if 13 <= len(digits) <= 19 and _luhn_ok(digits):
        return _keep_last4(digits)
    return m.group(0)


def mask_pii(text: str) -> str:
    if not text:
        return text
    text = _SECRET.sub(lambda m: f"{m.group(1)}{m.group(2)}{MASK * 6}", text)
    text = _SHORT_SECRET.sub(lambda m: f"{m.group(1)}{m.group(2)}{MASK * 6}", text)
    text = _SORT_CODE.sub(
        lambda m: f"{m.group(1)}{m.group(2)}{MASK * 2}-{MASK * 2}-{m.group(3)[-2:]}", text
    )
    text = _UK_ACCOUNT.sub(lambda m: f"{m.group(1)}{m.group(2)}{_keep_last4(m.group(3))}", text)
    text = _CARD.sub(_card, text)
    text = _IBAN.sub(lambda m: m.group(0)[:4] + " " + _keep_last4(m.group(0)), text)
    for rx in _NATIONAL_IDS:
        text = rx.sub(lambda m: _keep_last4(m.group(0)), text)
    return text


def mask_obj(value: object) -> object:
    """Mask every string inside a JSON-like value (event payloads)."""
    if isinstance(value, str):
        return mask_pii(value)
    if isinstance(value, dict):
        return {k: mask_obj(v) for k, v in value.items()}
    if isinstance(value, list):
        return [mask_obj(v) for v in value]
    return value


def _mask_arg(value: object) -> object:
    return mask_pii(value) if isinstance(value, str) else value


class PiiFilter(logging.Filter):
    """Logging filter: masks the formatted message of every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Mask the template and each argument, keeping their shape: formatters such as uvicorn's
        # access log unpack record.args, so it can't be replaced by the formatted string.
        if isinstance(record.msg, str):
            record.msg = mask_pii(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(_mask_arg(a) for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: _mask_arg(v) for k, v in record.args.items()}
        if record.exc_info and not record.exc_text:
            # Exception messages can quote user text; the formatter uses exc_text when it is set.
            record.exc_text = mask_pii(logging.Formatter().formatException(record.exc_info))
        return True


# uvicorn's loggers do not propagate to the root logger's filters: filter their handlers too.
LOGGERS = ("", "uvicorn", "uvicorn.error", "uvicorn.access")


def _add(target: logging.Logger | logging.Handler) -> None:
    if not any(isinstance(f, PiiFilter) for f in target.filters):
        target.addFilter(PiiFilter())


def install_log_filter(logger: logging.Logger | None = None) -> None:
    targets = [logger] if logger else [logging.getLogger(name) for name in LOGGERS]
    for target in targets:
        _add(target)
        for handler in target.handlers:
            _add(handler)
