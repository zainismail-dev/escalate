"""CodeQL py/polynomial-redos: every regex run on user text stays linear.

Each adversarial input is 100k characters with no terminator, the shape that made the old
patterns backtrack (overlapping `\\s*` runs, a lookahead rescanning the rest of the text).
The old patterns took seconds to hours on these; the new ones must finish in < 100 ms.
"""

import re
import time
from collections.abc import Callable

import pytest

from escalate import pii
from escalate.agent.fact_check import code_check, find_dates, find_ids, find_numbers
from escalate.agent.review import BLANK, blanks
from escalate.channels.email_smtp import EMAIL_RE

N = 100_000
BUDGET_S = 0.1


def _fastest(fn: Callable[[], object]) -> float:
    """Best of 3, so a busy CI runner doesn't fail a linear pattern."""
    best = float("inf")
    for _ in range(3):
        start = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - start)
    return best


def _finds(rx: re.Pattern[str], text: str) -> Callable[[], object]:
    return lambda: list(rx.finditer(text))


@pytest.mark.parametrize(
    ("rx", "text"),
    [
        (pii._SECRET, "password" + " " * N),
        (pii._SECRET, "password:" + " " * N),
        (pii._SECRET, "password is" + " " * N),
        (pii._SECRET, "pin = is :" + "\t" * N),
        (pii._SORT_CODE, "sort code" + " " * N + "x"),
        (pii._SORT_CODE, "sort code:" + " " * N + "x"),
        (pii._UK_ACCOUNT, "account" + " " * N + "x"),
        (pii._UK_ACCOUNT, "account number #" + " " * N + "x"),
    ],
    ids=["secret", "secret-colon", "secret-is", "secret-tabs", "sort", "sort-colon", "acct", "no"],
)
def test_pii_patterns_are_linear(rx: re.Pattern[str], text: str) -> None:
    assert _fastest(_finds(rx, text)) < BUDGET_S


def test_mask_pii_is_linear() -> None:
    text = "password" + " " * N
    assert _fastest(lambda: pii.mask_pii(text)) < BUDGET_S * 3  # every pattern, one pass each


@pytest.mark.parametrize(
    "text",
    ["[[" + " " * N, "[[ x" + " " * N, "[[" + "\n" * N + "x", "[[x\n" + " " * N, "[[" * (N // 2)],
    ids=["spaces", "text-spaces", "newlines", "trailing", "openers"],
)
def test_blank_pattern_is_linear(text: str) -> None:
    assert _fastest(_finds(BLANK, text)) < BUDGET_S


@pytest.mark.parametrize(
    "text",
    ["a@" + "a." * (N // 2) + "@", "a@" + "." * N + " ", "a@" + "a" * N + "@", "a" * N + "@"],
    ids=["labels", "dots", "one-label", "no-domain"],
)
def test_email_pattern_is_linear(text: str) -> None:
    assert _fastest(lambda: EMAIL_RE.match(text)) < BUDGET_S


@pytest.mark.parametrize(
    "text",
    ["a-" * (N // 2), "a-" * (N // 2) + "a_", "1-" * (N // 2) + "a", "a1-" * (N // 3) + "é"],
    ids=["letters", "underscore-tail", "digits", "unicode-tail"],
)
def test_id_extraction_is_linear(text: str) -> None:
    assert _fastest(lambda: find_numbers(text)) < BUDGET_S
    assert _fastest(lambda: find_ids(text)) < BUDGET_S


@pytest.mark.parametrize(
    "text",
    ["1 " * (N // 2) + "x", "1" + " " * N + "x", "1," * (N // 2) + "1a", "12 jan " * (N // 7)],
    ids=["groups", "spaces", "commas", "dates"],
)
def test_number_and_date_extraction_is_linear(text: str) -> None:
    assert _fastest(lambda: find_numbers(text)) < BUDGET_S
    assert _fastest(lambda: find_dates(text)) < BUDGET_S


def test_code_check_on_a_huge_draft_is_linear() -> None:
    draft = "a-" * (N // 2)
    assert _fastest(lambda: code_check(draft, {"order_id": "BM-48213"})) < BUDGET_S * 5


# Behaviour kept by the rewrites.


def test_secret_masking_unchanged() -> None:
    assert pii.mask_pii("password :  is : hunter2") == "password :  is : ••••••"
    assert pii.mask_pii("my PIN is 4321") == "my PIN is ••••••"
    assert pii.mask_pii("password\n\nhunter2") == "password\n\n••••••"
    assert pii.mask_pii("password   ") == "password   "
    assert pii.mask_pii("sort code:  12-34-56") == "sort code:  ••-••-56"
    assert pii.mask_pii("account no. # 12345678") == "account no. # •••• 5678"


def test_blanks_unchanged() -> None:
    assert blanks("a ____ b [[ x ]]") == ["____", "x"]
    assert blanks("[[x\n]] and [[\n  your phone ]]") == ["x", "your phone"]
    assert blanks("[[\n]] [[a\nb]] [[]]") == []
    assert blanks("[[[name]]]") == ["name"]
    spans = [m.span() for m in BLANK.finditer("Hi [[ sign ]].")]
    assert spans == [(3, 13)]


def test_numbers_and_ids_unchanged() -> None:
    assert find_numbers("pay 45 000abc") == {"45"}
    assert find_numbers("PKR 64,500.00 and 1,234.5x") == {"64500", "1234"}
    assert find_numbers("order BM-48213 on 2026-01-05, 7 items") == {"7"}
    assert find_ids("refs BM-48213, ml-7781-sb, 10-12, AB-CD") == {"BM-48213", "ML-7781-SB"}


def test_email_pattern_accepts_real_addresses_only() -> None:
    for ok in ["a@b.co", "first.last+tag@mail.example.org", "x@sub.domain.museum"]:
        assert EMAIL_RE.match(ok), ok
    for bad in ["a@b", "a@b..c", "a@.b.c", "a@b.c.", "a b@c.d", "a@b.c\n", "@b.c", "a@@b.c"]:
        assert not EMAIL_RE.match(bad), bad
