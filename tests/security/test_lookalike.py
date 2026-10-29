"""Second review N8: a look-alike recipient (Cyrillic "а" in a Latin address) planted in
evidence looked identical on the confirmation screen."""

import pytest

from escalate.recipients import check_lookalike

CYRILLIC_A = "а"


@pytest.mark.parametrize("addr", ["support@brightmart.example", "a.b+c@x-y.example", None, ""])
def test_plain_ascii_addresses_are_not_flagged(addr: str | None) -> None:
    assert check_lookalike(addr).warn is False


def test_mixed_script_lookalike_is_flagged_with_punycode() -> None:
    addr = f"refunds@p{CYRILLIC_A}ypal.example"
    look = check_lookalike(addr)
    assert look.warn is True
    assert look.scripts == ["CYRILLIC", "LATIN"]
    assert look.ascii_form is not None
    assert look.ascii_form.startswith("refunds@xn--") and look.ascii_form.isascii()
    assert look.ascii_form != "refunds@paypal.example"  # the look-alike is visible


def test_single_non_latin_script_still_warns() -> None:
    look = check_lookalike("инфо@пример.рф")  # one script, but still not what it may seem
    assert look.warn is True and look.scripts == ["CYRILLIC"]
    assert look.ascii_form == "инфо@xn--e1afmkfd.xn--p1ai"  # the domain as mail servers see it


def test_review_api_shows_the_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    from escalate.api.routes.messages import recipient_check
    from escalate.db.models import Case, Message

    case = Case(description="x", playbook_id=None, facts=[], evidence=[], messages=[])
    msg = Message(case=case, step_id="s1", recipient=f"help@n{CYRILLIC_A}rthline.example")
    out = recipient_check(msg)
    assert out.lookalike is True and out.scripts == ["CYRILLIC", "LATIN"]
    assert out.ascii_form and out.ascii_form.startswith("help@xn--")
