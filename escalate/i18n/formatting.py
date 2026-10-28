"""Locale-aware money and date formatting with Babel. Currencies are ISO 4217 codes."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from babel import Locale, UnknownLocaleError
from babel.dates import format_date as _babel_date
from babel.numbers import format_currency


def _locale(locale: str | None) -> str:
    try:
        return str(Locale.parse((locale or "en").replace("-", "_")))
    except (UnknownLocaleError, ValueError):
        return "en"


def to_decimal(amount: object) -> Decimal | None:
    if isinstance(amount, Decimal):
        return amount
    text = str(amount).strip().replace(",", "")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def format_money(amount: object, currency: str | None, locale: str | None = "en") -> str:
    """45000, "PKR", "en_PK" -> "Rs 45,000.00". Falls back to the raw text if it isn't a number."""
    value = to_decimal(amount)
    if value is None or not currency:
        return f"{amount} {currency or ''}".strip()
    return format_currency(value, currency.upper(), locale=_locale(locale))


def format_date(d: date | datetime | str, locale: str | None = "en", fmt: str = "long") -> str:
    if isinstance(d, str):
        try:
            parsed: date | datetime = date.fromisoformat(d[:10])
        except ValueError:
            return d
    else:
        parsed = d
    return str(_babel_date(parsed, format=fmt, locale=_locale(locale)))
