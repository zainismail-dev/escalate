"""Locale-aware money and date formatting with Babel. Currencies are ISO 4217 codes."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from babel import Locale, UnknownLocaleError
from babel.dates import format_date as _babel_date
from babel.numbers import format_currency, get_currency_symbol


def _locale(locale: str | None) -> str:
    try:
        return str(Locale.parse((locale or "en").replace("-", "_")))
    except (UnknownLocaleError, ValueError):
        lang = (locale or "en").replace("-", "_").split("_")[0]
        return lang if lang != locale and _known(lang) else "en"


def _known(locale: str) -> bool:
    try:
        Locale.parse(locale)
        return True
    except (UnknownLocaleError, ValueError):
        return False


def locale_for(language: str | None, country: str | None = None) -> str:
    """("en", "PK") -> "en_PK" when Babel knows it, else the language alone."""
    lang = (language or "en").lower()
    if country and len(country) == 2 and _known(f"{lang}_{country.upper()}"):
        return f"{lang}_{country.upper()}"
    return _locale(lang)


def to_decimal(amount: object) -> Decimal | None:
    if isinstance(amount, Decimal):
        return amount
    text = str(amount).strip().replace(",", "")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def format_money(amount: object, currency: str | None, locale: str | None = "en") -> str:
    """45000, "PKR", "en_PK" -> "PKR 45,000.00".

    The ISO code replaces the symbol so letters are unambiguous ("$" is many currencies);
    grouping and decimals follow the locale. Non-numbers come back as written.
    """
    value = to_decimal(amount)
    if value is None or not currency:
        return f"{amount} {currency or ''}".strip()
    code, loc = currency.upper(), _locale(locale)
    text = format_currency(value, code, locale=loc).replace("\xa0", " ").replace("\u202f", " ")
    symbol = get_currency_symbol(code, locale=loc)
    if symbol != code:
        text = text.replace(symbol, f" {code} ")
    elif code in text and not text.startswith(f"{code} ") and text.startswith(code):
        text = text.replace(code, f"{code} ", 1)
    return " ".join(text.split())


def format_date(d: date | datetime | str, locale: str | None = "en", fmt: str = "long") -> str:
    if isinstance(d, str):
        try:
            parsed: date | datetime = date.fromisoformat(d[:10])
        except ValueError:
            return d
    else:
        parsed = d
    return str(_babel_date(parsed, format=fmt, locale=_locale(locale)))
