"""Locale-aware money and date formatting with Babel. Currencies are ISO 4217 codes."""

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from functools import lru_cache

from babel import Locale, UnknownLocaleError, localedata
from babel.dates import format_date as _babel_date
from babel.numbers import format_currency, get_currency_precision, get_currency_symbol


def _locale(locale: str | None) -> str:
    try:
        return str(Locale.parse((locale or "en").replace("-", "_")))
    except (UnknownLocaleError, ValueError):
        lang = (locale or "en").replace("-", "_").split("_")[0]
        return lang if lang != locale and _known(lang) else "en"


@lru_cache
def _identifiers() -> frozenset[str]:
    return frozenset(localedata.locale_identifiers())


def _known(locale: str) -> bool:
    """Only locales CLDR really has data for (Babel also accepts e.g. en_ZZ, 'unknown region')."""
    return locale in _identifiers()


def locale_for(language: str | None, country: str | None = None) -> str:
    """("en", "PK") -> "en_PK" when Babel knows it, else the language alone. A BCP-47 tag's own
    region wins over the country: ("en-GB", "PK") -> "en_GB"."""
    lang, _, tag_region = (language or "en").replace("_", "-").partition("-")
    lang = lang.lower()
    for reg in (tag_region.upper(), (country or "").upper()):
        if len(reg) == 2 and _known(f"{lang}_{reg}"):
            return f"{lang}_{reg}"
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


_SPACES = re.compile(r"[\s\u202f\u00a0]+")


def format_amount(amount: object, currency: str | None, locale: str | None = "en") -> str | None:
    """Money for people to read (API responses, web UI, PDF): the locale's own symbol and
    spacing, no decimals for whole amounts, the currency's digits otherwise.

    64500 PKR en_PK -> "Rs 64,500"; 39.99 GBP en_GB -> "£39.99"; 89.9 EUR de_DE -> "89,90 €".
    Spaces are U+00A0. The web app's formatter (web/src/lib/money.ts) follows the same rules;
    both are tested against schema/money_format_cases.json. Letters use `format_money` instead.
    """
    value = to_decimal(amount)
    if value is None:
        return None if amount in (None, "") else str(amount)
    if not currency:
        return f"{value.normalize():f}"
    code, loc = currency.upper(), _locale(locale)
    digits = 0 if value == value.to_integral_value() else get_currency_precision(code)
    pattern = Locale.parse(loc).currency_formats["standard"].pattern
    pattern = re.sub(r"0\.0+", "0." + "0" * digits if digits else "0", pattern)
    text = format_currency(value, code, locale=loc, format=pattern, currency_digits=False)
    return _currency_spacing(_SPACES.sub("\u00a0", text), get_currency_symbol(code, locale=loc))


def _currency_spacing(text: str, symbol: str) -> str:
    """CLDR currency spacing (Babel skips it): a symbol that ends or starts with a letter is
    kept apart from the digits ("Rs 64,500", but "$1,249")."""

    def letter(ch: str) -> bool:
        return unicodedata.category(ch).startswith("L")

    head, tail = text[len(symbol) :], text[: -len(symbol)]
    if text.startswith(symbol) and head[:1].isdigit() and letter(symbol[-1]):
        return f"{symbol}\u00a0{head}"
    if text.endswith(symbol) and tail[-1:].isdigit() and letter(symbol[0]):
        return f"{tail}\u00a0{symbol}"
    return text


def format_date(d: date | datetime | str, locale: str | None = "en", fmt: str = "long") -> str:
    if isinstance(d, str):
        try:
            parsed: date | datetime = date.fromisoformat(d[:10])
        except ValueError:
            return d
    else:
        parsed = d
    return str(_babel_date(parsed, format=fmt, locale=_locale(locale)))
