import json
from datetime import date
from pathlib import Path

import pytest

from escalate.i18n.formatting import format_date, format_money, locale_for

LOCALES = Path(__file__).resolve().parents[1] / "locales"


@pytest.mark.parametrize(
    ("amount", "currency", "locale", "expected"),
    [
        ("45000", "PKR", "en_PK", "PKR 45,000.00"),
        (45000, "PKR", "ur_PK", "PKR 45,000.00"),
        ("4500000", "INR", "en_IN", "INR 45,00,000.00"),  # lakh grouping
        ("1999.5", "INR", "hi_IN", "INR 1,999.50"),
        ("899", "GBP", "en_GB", "GBP 899.00"),
        ("15.99", "USD", "en_US", "USD 15.99"),
        ("1,234.5", "USD", "en", "USD 1,234.50"),
        ("549", "EUR", "de_DE", "549,00 EUR"),
    ],
)
def test_format_money(amount: object, currency: str, locale: str, expected: str) -> None:
    assert format_money(amount, currency, locale) == expected


def test_format_money_non_number_is_left_alone() -> None:
    assert format_money("about forty thousand", "PKR") == "about forty thousand PKR"
    assert format_money("100", None) == "100"


def test_format_date() -> None:
    d = date(2026, 11, 4)
    assert format_date(d, "en_GB") == "4 November 2026"
    assert format_date(d, "en_US") == "November 4, 2026"
    assert format_date("2026-11-04", "en_PK") == "4 November 2026"
    assert format_date("not a date", "en") == "not a date"
    assert "2026" in format_date(d, "ur_PK")


def test_locale_for() -> None:
    assert locale_for("en", "PK") == "en_PK"
    assert locale_for("en", "ZZ") == "en"
    assert locale_for("xx", None) == "en"
    assert locale_for("hi", "IN") == "hi_IN"


def test_locale_files_share_keys() -> None:
    en = json.loads((LOCALES / "en.json").read_text())
    for path in LOCALES.glob("*.json"):
        other = json.loads(path.read_text())
        assert set(other) <= set(en), f"{path.name} has keys missing from en.json"
        for key, value in other.items():
            assert set(_placeholders(value)) == set(_placeholders(en[key])), (path.name, key)


def _placeholders(text: str) -> list[str]:
    import re

    return re.findall(r"\{(\w+)\}", text)


def test_format_amount_matches_the_shared_cases() -> None:
    """The same table the web formatter is tested against (web/tests/money.test.mts)."""
    import json
    from pathlib import Path

    from escalate.i18n.formatting import format_amount

    data = json.loads((Path(__file__).parents[1] / "schema/money_format_cases.json").read_text())
    for c in data["cases"]:
        assert format_amount(c["amount"], c["currency"], c["locale"]) == c["expected"], c


def test_format_amount_edges() -> None:
    from escalate.i18n.formatting import format_amount

    assert format_amount(None, "USD", "en_US") is None
    assert format_amount("about forty", "USD", "en_US") == "about forty"
    assert format_amount("12.50", None) == "12.5"
