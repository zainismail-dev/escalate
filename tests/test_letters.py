"""The letter a consumer actually gets: complete, natural, facts only, from the model or the
fallback template. And what a rewrite from a reasoning model must get past the fact check."""

import logging
import re
from typing import Any

import pytest
from freezegun import freeze_time

from escalate.agent import runner
from escalate.agent.draft import draft_step
from escalate.agent.fact_check import (
    FactCheckResult,
    code_check,
    dropped_values,
    fact_check,
    find_ids,
    find_numbers,
    model_check,
)
from escalate.playbooks import loader
from escalate.playbooks.loader import get_playbook
from escalate.templates_engine import render_step
from tests.agent_env import AgentEnv, agent_env, make_llm, template_parts  # noqa: F401
from tests.factories import led_case
from tests.fakes.fake_llm import FakeLLM

UK = {
    "buyer_name": "Sam Lee",
    "seller_name": "Acme Ltd",
    "seller_contact": "help@acme.example",
    "product": "kettle",
    "order_id": "AC-10234",
    "order_date": "2026-10-01",
    "amount": "39.99",
    "currency": "GBP",
    "defect_description": "stopped working after a week",
    "remedy_wanted": "refund",
    "refused_on": "2026-10-15",
    "refusal_text": "we do not refund opened items",
}
TODAY = "2026-11-02"


def uk_letter(**over: Any) -> str:
    pb = get_playbook("gb-general-refund-refused")
    facts = {k: v for k, v in {**UK, **over}.items() if v is not None}
    with freeze_time(TODAY):
        r = render_step(pb, pb.steps[0], facts, "en", country="GB")
    return f"{r.subject}\n{r.body}"


@pytest.fixture(autouse=True)
def _fresh() -> None:
    loader.clear_cache()


def test_the_uk_letter_has_everything_it_must() -> None:
    text = uk_letter()
    for needle in (
        "a kettle",
        "AC-10234",
        "1 October 2026",
        "The problem is that it stopped working after a week.",
        'On 15 October 2026 you refused, saying: "we do not refund opened items".',
        "a refund of GBP 39.99",
        "Consumer Rights Act 2015",
        "short-term right to reject",
        "within 14 days, by 16 November 2026",
    ):
        assert needle in text, needle
    assert not re.search(r"\d{4}-\d{2}-\d{2}", text)  # never an ISO date


def test_the_fallback_template_reads_as_a_letter() -> None:
    text = uk_letter()
    assert "The problem:" not in text
    assert "I ask you to provide the following" not in text
    assert "None" not in text


def test_without_their_words_the_refusal_still_reads_well() -> None:
    text = uk_letter(refusal_text=None)
    assert "On 15 October 2026 you refused my request." in text
    assert "\n\n\n" not in text


def test_the_letter_before_action_has_the_same_content() -> None:
    pb = get_playbook("gb-general-refund-refused")
    with freeze_time(TODAY):
        r = render_step(pb, pb.steps[1], UK, "en", country="GB")
    for needle in (
        "a kettle",
        "1 October 2026",
        "you refused",
        "Consumer Rights Act 2015",
        "a refund of GBP 39.99",
        "within 14 days, by 16 November 2026",
    ):
        assert needle in r.body, needle
    assert "\n\n\n" not in r.body


@pytest.mark.parametrize(
    ("product", "named"),
    [
        ("kettle", "a kettle"),
        ("oven", "an oven"),
        ("43 inch LED TV", "a 43 inch LED TV"),
        ("wireless earbuds", "wireless earbuds"),
        ("the blender", "the blender"),
    ],
)
def test_the_product_reads_naturally(product: str, named: str) -> None:
    assert f"I bought {named} from you" in uk_letter(product=product)


def test_the_short_term_right_only_appears_when_it_can_apply() -> None:
    late = uk_letter(order_date="2026-08-01", refused_on=None, refusal_text=None)
    assert "Consumer Rights Act 2015" in late and "short-term right" not in late
    raised_in_time = uk_letter(order_date="2026-10-01", refused_on="2026-10-29")
    assert "short-term right to reject" in raised_in_time


@pytest.mark.parametrize("product", ["kettle", "wireless earbuds"])
def test_the_short_term_right_reads_right_for_one_item_or_a_pair(product: str) -> None:
    letter = uk_letter(product=product, order_date="2026-10-01", refused_on="2026-10-29")
    assert "I raised this within 30 days of the purchase, so" in letter
    assert "buying them" not in letter


def test_a_pack_without_a_legal_basis_cites_no_law() -> None:
    pb = get_playbook("us-general-refund-refused")
    r = render_step(pb, pb.steps[0], UK, "en", country="US")
    assert "Consumer Rights Act" not in r.body and "right to reject" not in r.body
    assert "a kettle" in r.body and "October 1, 2026" in r.body  # the locale's own long format


def test_every_new_number_in_the_template_is_in_its_own_reference() -> None:
    text = uk_letter()
    assert code_check(text, UK, text) == []


@pytest.mark.parametrize(
    ("remedy", "wanted"),
    [
        ("refund", "a refund of GBP 39.99"),
        ("a full refund", "a full refund of GBP 39.99"),
        ("a replacement or a refund", "a replacement or a refund of GBP 39.99"),
        ("repair", "a repair, for the GBP 39.99 I paid"),
        ("a partial refund of 10", "a partial refund of 10"),
    ],
)
def test_the_remedy_carries_the_amount(remedy: str, wanted: str) -> None:
    assert f"I ask for {wanted}." in uk_letter(remedy_wanted=remedy)


@pytest.mark.parametrize(
    ("fault", "sentence"),
    [
        ("Stopped working.", "The problem is that it stopped working."),
        ("The screen cracked", "The problem is that the screen cracked."),
        ("Screen cracked", "What went wrong: Screen cracked."),
    ],
)
def test_a_fault_becomes_a_sentence(fault: str, sentence: str) -> None:
    assert sentence in uk_letter(defect_description=fault)


# --- what the fact check rejected ---------------------------------------------------

REFERENCE = uk_letter()


def test_a_letter_may_say_14_day_and_30_day_when_the_template_does() -> None:
    draft = "You have a 14-day period. The 30-day short-term right to reject applies."
    assert code_check(draft, UK, REFERENCE) == []


def test_an_invented_period_is_still_rejected_however_it_is_written() -> None:
    assert code_check("within 99 days", UK, REFERENCE) == ["number 99 is not in the case facts"]
    assert code_check("a 99-day period", UK, REFERENCE) == ["number 99 is not in the case facts"]
    assert code_check("a 99‑day period", UK, REFERENCE) == ["number 99 is not in the case facts"]


def test_a_number_and_a_word_is_not_an_id_but_an_upper_case_tail_still_is() -> None:
    assert find_ids("a 14-day period") == set() and find_numbers("a 14-day period") == {"14"}
    assert find_ids("order 123-ABC") == {"123-ABC"}


def test_non_breaking_hyphens_and_narrow_spaces_are_ordinary_values() -> None:
    assert code_check("order AC‑10234 on 1 October 2026", UK, REFERENCE) == []
    assert code_check("order ZZ‑10234", UK, REFERENCE) == ["ID ZZ-10234 is not in the case facts"]


def test_a_rewrite_that_loses_a_value_is_noticed() -> None:
    assert dropped_values(REFERENCE, REFERENCE) == []
    gone = dropped_values(REFERENCE.replace("16 November 2026", "soon"), REFERENCE)
    assert gone == ["keep 2026-11-16 from the template"]
    assert dropped_values(REFERENCE.replace("AC-10234", "your order"), REFERENCE)


def test_the_model_check_sees_the_template_and_cannot_flag_its_words() -> None:
    llm = FakeLLM(
        rules=[
            (
                "List every factual claim",
                {"unsupported": ["Consumer Rights Act 2015", "It caught fire"]},
            )
        ]
    )
    found = model_check("draft", UK, llm, reference=REFERENCE)
    assert found == ["It caught fire"]
    assert "short-term right to reject" in llm.calls[0][0]  # the trusted letter is in the prompt


def test_categories_name_the_reason_and_never_the_value() -> None:
    result = FactCheckResult(
        code_issues=["number 99 is not in the case facts", "ID ZZ-1 is not in the case facts"],
        model_issues=["It caught fire"],
        tone_issues=["wording: 'crooks'"],
        omissions=["keep 2026-11-16 from the template"],
    )
    assert result.categories == [
        "dropped_value",
        "invented_id",
        "invented_number",
        "model_unsupported",
        "tone",
    ]


def test_keep_values_is_off_for_a_users_own_edit() -> None:
    assert fact_check("I only say this.", UK, REFERENCE, use_model=False).ok
    assert not fact_check("I only say this.", UK, REFERENCE, use_model=False, keep_values=True).ok


# --- the whole loop --------------------------------------------------------------------

UK_TEXT = "I bought a kettle from Acme on 1 October 2026 for £39.99. It stopped working."


def gpt_oss_rewrite(prompt: str, _slot: Any) -> dict[str, str]:
    """A rewrite in gpt-oss's habits: U+2011 hyphens, U+202F in dates, "14-day", the same values."""
    subject, body = template_parts(prompt)
    body = body.replace("AC-10234", "AC‑10234").replace("1 October 2026", "1 October 2026")
    body += "\n\nYou have this 14-day period to respond; the 30-day period is set out above."
    return {"subject": subject, "body": body}


def uk_env(env: AgentEnv, draft: Any = gpt_oss_rewrite, **kw: Any) -> int:
    llm = make_llm(UK, {"country": "GB", "region": None, "reason": "refund"}, **kw)
    llm.rules = [(n, draft if n == "You write the" else r) for n, r in llm.rules]
    from escalate.llm import set_llm

    set_llm(llm)
    env.llm = llm
    return env.new_case(description=UK_TEXT, country="GB", language="en", currency="GBP")


def test_a_reasoning_models_rewrite_is_accepted_and_cleaned(
    agent_env: AgentEnv,  # noqa: F811
) -> None:
    case_id = uk_env(agent_env)
    with freeze_time(TODAY):
        result = runner.start_case(case_id)
    assert result.waiting_for == "approve_draft"
    body = result.pending["draft"]["body"]  # type: ignore[index]
    assert "14-day period" in body  # the model's letter, not the fallback
    assert "AC-10234" in body and "1 October 2026" in body  # plain hyphens and spaces
    assert "draft_template_used" not in agent_env.event_types(case_id)


def test_a_rejected_rewrite_ends_in_the_natural_template_with_reasons_logged(
    agent_env: AgentEnv,  # noqa: F811
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_value = "12345"
    case_id = uk_env(
        agent_env,
        {"subject": "S", "body": f"I paid {secret_value} for the kettle, order AC-10234."},
    )
    with freeze_time(TODAY), caplog.at_level(logging.WARNING, "uvicorn.error"):
        result = runner.start_case(case_id)
    body = result.pending["draft"]["body"]  # type: ignore[index]
    assert "The problem is that it stopped working after a week." in body
    assert "within 14 days, by 16 November 2026" in body

    assert "invented_number" in caplog.text and "attempts_exhausted" in caplog.text
    assert secret_value not in caplog.text
    with agent_env.session() as s:
        from sqlalchemy import select

        from escalate.db.models import Event

        checks = s.scalars(select(Event).where(Event.type == "fact_checked")).all()
        assert all("issues" not in e.payload for e in checks)
        assert "invented_number" in checks[0].payload["categories"]


def test_a_model_that_never_returns_json_falls_back_and_says_why(
    agent_env: AgentEnv,  # noqa: F811
) -> None:
    case_id = uk_env(agent_env, "Sorry, here is your letter.")
    with freeze_time(TODAY):
        result = runner.start_case(case_id)
    assert "within 14 days" in result.pending["draft"]["body"]  # type: ignore[index]
    with agent_env.session() as s:
        from sqlalchemy import select

        from escalate.db.models import Event

        used = s.scalars(select(Event).where(Event.type == "draft_template_used")).first()
        assert used is not None and used.payload == {"reason": "invalid_json"}


def test_an_iso_date_from_the_model_or_a_free_text_fact_is_spelled_out(
    db: Any,
    settings: object,
) -> None:
    case = led_case(db, country="GB")
    pb = get_playbook("gb-general-refund-refused")
    from escalate.db.models import CaseFact

    db.add(CaseFact(case_id=case.id, key="product", value="LED TV"))
    db.flush()
    db.refresh(case)
    llm = FakeLLM(script=[{"subject": "On 2026-10-01", "body": "Bought on 2026-10-01."}])
    msg = draft_step(db, case, pb, pb.steps[0], llm=llm)
    assert "1 October 2026" in msg.body and "1 October 2026" in (msg.subject or "")
    assert "2026-10-01" not in msg.body
