from pathlib import Path

import pytest

from escalate.agent.tone import tone_flags
from evals.run import field_ok, load_cases, load_replies, main, norm


def test_golden_set_coverage() -> None:
    cases = load_cases()
    assert len(cases) >= 50
    assert len({c["country"] for c in cases}) >= 5
    assert len({c["language"] for c in cases}) >= 3
    assert {c["case_type"] for c in cases} == {"refund_refused", "subscription_cancel", "scam"}
    assert len({c["id"] for c in cases}) == len(cases)
    led = next(c for c in cases if c["id"] == "pk-led-8-months")
    assert "claim is approved" in led["user_text"]


def test_replies_cover_every_verdict() -> None:
    replies = load_replies()
    assert len(replies) >= 40
    assert {r["expected"] for r in replies} == {"resolved", "partial", "refused", "no_reply"}
    led = [r for r in replies if "company claim is approved" in r["reply_text"]]
    assert led and all(r["expected"] == "refused" for r in led)


def test_norm_and_field_ok() -> None:
    assert norm("45,000.00") == "45000"
    assert field_ok("amount", "45000", "45,000")
    assert field_ok("remedy_wanted", "replacement refund", "A replacement or a full refund")
    assert not field_ok("order_id", "BM-48213", "BM-48214")
    assert not field_ok("order_id", "BM-48213", None)


def test_all_suites_run_with_oracle(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report = tmp_path / "report.md"
    assert main(["--suite", "all", "--llm", "oracle", "--report", str(report)]) == 0
    text = report.read_text()
    for row in (
        "Fact extraction field accuracy",
        "Case type + country + region",
        "Unsupported facts in drafts",
        "Drafts flagged for threats or rudeness",
        "Reply verdict correct",
    ):
        assert row in text
    assert "Oracle run" in text
    assert "❌" not in text


@pytest.mark.parametrize(
    "text",
    [
        "You are idiots and liars.",
        "Refund me or else you will regret it.",
        "I will make this go viral and destroy your business.",
        "REFUND MY MONEY RIGHT NOW PLEASE",
        "Answer me!!!",
    ],
)
def test_tone_flags_catch_threats_and_insults(text: str) -> None:
    assert tone_flags(text)


@pytest.mark.parametrize(
    "text",
    [
        "LEGAL NOTICE\n\nIf you fail to do so, I will file a complaint before the court.",
        "BEFORE THE DISTRICT CONSUMER COURT",
        "I reported the fraudsters who contacted me to the police.",
        "Please reply by 4 November 2026. Yours sincerely, Ali",
    ],
)
def test_tone_flags_allow_firm_polite_letters(text: str) -> None:
    assert tone_flags(text) == []


def test_report_keeps_history_section(tmp_path: Path) -> None:
    report = tmp_path / "report.md"
    report.write_text("# old\n\n## History\n\n| 2026 | baseline |\n")
    main(["--suite", "replies", "--llm", "oracle", "--report", str(report)])
    text = report.read_text()
    assert text.startswith("# Eval report")
    assert "| 2026 | baseline |" in text
