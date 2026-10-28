from evals.run import field_ok, load_cases, main, norm


def test_golden_cases_have_the_led_case() -> None:
    cases = load_cases()
    assert len(cases) >= 10
    led = next(c for c in cases if c["id"] == "pk-led-8-months")
    assert "claim is approved" in led["user_text"]


def test_norm_and_field_ok() -> None:
    assert norm("45,000.00") == "45000"
    assert field_ok("amount", "45000", "45,000")
    assert field_ok("remedy_wanted", "replacement refund", "A replacement or a full refund")
    assert not field_ok("order_id", "BM-48213", "BM-48214")
    assert not field_ok("order_id", "BM-48213", None)


def test_extraction_suite_runs_with_oracle(capsys: object) -> None:
    assert main(["--suite", "extraction", "--llm", "oracle"]) == 0
    out = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "extraction: 100.0%" in out
