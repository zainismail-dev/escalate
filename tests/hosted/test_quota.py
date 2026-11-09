"""Hosted limits: open cases per user, AI calls per user per day, a global daily AI budget and
per-user rate limits. Refusals are friendly and count nothing."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from freezegun import freeze_time
from sqlalchemy import Engine

from escalate.config import get_settings
from escalate.db.models import GLOBAL_USAGE
from escalate.db.session import session_scope
from escalate.db.tenancy import as_user
from escalate.llm import get_llm
from escalate.llm.client import LLMBadOutput, LLMMisconfigured
from escalate.llm.quota import AiBusy, AiDailyLimit, calls_today, charge, refund
from tests.factories import LED_TEXT
from tests.hosted.conftest import WEB_ORIGIN, Hosted

A, B = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"


def used(user: str) -> int:
    with session_scope() as s:
        return calls_today(s, user)


def test_calls_are_counted_per_user_and_globally(hosted_db: Engine) -> None:
    for _ in range(3):
        charge(A)
    charge(B)
    assert (used(A), used(B), used(GLOBAL_USAGE)) == (3, 1, 4)


def test_the_daily_user_limit_refuses_and_counts_nothing_more(
    hosted_db: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_CALLS_PER_DAY", "2")
    get_settings.cache_clear()
    charge(A)
    charge(A)
    with pytest.raises(AiDailyLimit, match="Try again tomorrow"):
        charge(A)
    assert used(A) == 2 and used(GLOBAL_USAGE) == 2
    charge(B)  # other users are unaffected


def test_limits_reset_the_next_utc_day(hosted_db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_CALLS_PER_DAY", "1")
    get_settings.cache_clear()
    with freeze_time(datetime(2026, 10, 1, 23, 59)):
        charge(A)
        with pytest.raises(AiDailyLimit):
            charge(A)
    with freeze_time(datetime(2026, 10, 2, 0, 1)):
        charge(A)


def test_the_global_budget_says_the_ai_is_busy(
    hosted_db: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GLOBAL_AI_CALLS_PER_DAY", "2")
    get_settings.cache_clear()
    charge(A)
    charge(B)
    with pytest.raises(AiBusy, match="The AI is busy today, try tomorrow"):
        charge(A)
    assert used(GLOBAL_USAGE) == 2 and used(A) == 1


def test_get_llm_charges_the_current_user(hosted_db: Engine) -> None:
    from escalate.llm import set_llm
    from tests.fakes.fake_llm import FakeLLM

    set_llm(FakeLLM(rules=[("ping", "pong")]))
    try:
        with as_user(A):
            assert get_llm().complete("ping") == "pong"
        assert used(A) == 1
    finally:
        set_llm(None)


def new_case(client: TestClient, n: int = 0) -> str:
    r = client.post("/cases", json={"description": f"{LED_TEXT} #{n}", "country": "PK"})
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def test_three_open_cases_per_user(hosted: Hosted) -> None:
    alice, bob = hosted.account("alice@example.com"), hosted.account("bob@example.com")
    ids = [new_case(alice.client, n) for n in range(3)]
    r = alice.client.post("/cases", json={"description": LED_TEXT})
    assert r.status_code == 409 and r.json()["quota"] == "open_cases"
    assert "3 open cases" in r.json()["detail"]
    new_case(bob.client)  # per user
    assert alice.client.post(f"/cases/{ids[0]}/withdraw", json={}).status_code == 200
    new_case(alice.client, 9)  # a withdrawn case doesn't count


def with_evidence(client: TestClient) -> str:
    cid = new_case(client)
    client.post(f"/cases/{cid}/evidence", files={"file": ("r.txt", b"BM-48213", "text/plain")})
    return cid


def test_running_out_of_ai_calls_is_a_friendly_429(
    hosted: Hosted, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_CALLS_PER_DAY", "1")
    get_settings.cache_clear()
    alice = hosted.account("alice@example.com")
    r = alice.client.post(f"/cases/{with_evidence(alice.client)}/start")
    assert r.status_code == 429, r.text
    assert r.json()["quota"] == "user" and "Try again tomorrow" in r.json()["detail"]
    assert alice.client.get("/me").json()["ai_calls_today"] == 1


def test_the_global_budget_is_a_friendly_429(
    hosted: Hosted, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GLOBAL_AI_CALLS_PER_DAY", "0")
    get_settings.cache_clear()
    alice = hosted.account("alice@example.com")
    r = alice.client.post(f"/cases/{with_evidence(alice.client)}/start")
    assert r.status_code == 429
    assert r.json() == {"detail": "The AI is busy today, try tomorrow.", "quota": "global"}
    assert hosted.llm.calls == []  # nothing reached the model


def test_rate_limits_are_per_user(hosted: Hosted, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_WRITES_PER_MINUTE", "2")
    get_settings.cache_clear()
    from escalate.api.main import create_app

    hosted.app = create_app(startup=False)  # the limiter is per app
    alice, bob = hosted.account("alice@example.com"), hosted.account("bob@example.com")
    for _ in range(2):
        assert alice.client.put("/settings", json={"default_country": "GB"}).status_code == 200
    assert alice.client.put("/settings", json={"default_country": "GB"}).status_code == 429
    assert bob.client.put("/settings", json={"default_country": "GB"}).status_code == 200


# --- only successful completions count ------------------------------------------------------


def _failures() -> list[Exception]:
    import httpx
    import openai

    req = httpx.Request("POST", "https://api.groq.test/openai/v1/chat/completions")
    return [
        openai.InternalServerError("x", response=httpx.Response(500, request=req), body=None),
        openai.NotFoundError("x", response=httpx.Response(404, request=req), body=None),
        openai.RateLimitError("x", response=httpx.Response(429, request=req), body=None),
        openai.APITimeoutError(request=req),
        openai.APIConnectionError(request=req),
        LLMMisconfigured(404),
        LLMBadOutput("empty"),
    ]


@pytest.mark.parametrize("n", range(7))
def test_a_failed_call_counts_against_neither_limit(hosted_db: Engine, n: int) -> None:
    from escalate.llm import set_llm
    from tests.fakes.fake_llm import FakeLLM

    set_llm(FakeLLM(script=[_failures()[n]]))
    try:
        with as_user(A), pytest.raises(type(_failures()[n])):
            get_llm().complete("ping")
        assert (used(A), used(GLOBAL_USAGE)) == (0, 0)
    finally:
        set_llm(None)


def test_failures_never_use_up_the_daily_limit(
    hosted_db: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from escalate.llm import set_llm
    from tests.fakes.fake_llm import FakeLLM

    monkeypatch.setenv("AI_CALLS_PER_DAY", "2")
    get_settings.cache_clear()
    set_llm(FakeLLM(script=[LLMBadOutput("x") for _ in range(5)] + ["ok", "ok", "too many"]))
    try:
        with as_user(A):
            for _ in range(5):
                with pytest.raises(LLMBadOutput):
                    get_llm().complete("ping")
            assert get_llm().complete("ping") == "ok"
            assert get_llm().complete("ping") == "ok"
            with pytest.raises(AiDailyLimit):
                get_llm().complete("ping")
        assert used(A) == 2 and used(GLOBAL_USAGE) == 2
    finally:
        set_llm(None)


def test_a_call_failing_past_midnight_is_refunded_on_the_day_it_was_charged(
    hosted_db: Engine,
) -> None:
    with freeze_time(datetime(2026, 10, 1, 23, 59)):
        day = charge(A)
        refund(A, day)
        assert used(A) == 0
    with freeze_time(datetime(2026, 10, 2, 0, 1)):
        charge(A)
        refund(A, day)  # yesterday's count is 0 already: today's is untouched
        assert used(A) == 1


def test_json_mode_reaches_the_model_through_the_meter(hosted_db: Engine) -> None:
    from escalate.llm import set_llm

    seen: list[bool] = []

    class Spy:
        def complete(self, prompt: str, slot: str = "smart", json_mode: bool = False) -> str:
            seen.append(json_mode)
            return "{}"

    set_llm(Spy())  # type: ignore[arg-type]
    try:
        with as_user(A):
            get_llm().complete("ping", json_mode=True)
        assert seen == [True]
    finally:
        set_llm(None)


# --- a permanent AI error fails fast, and the browser can read it ---------------------------


def test_a_misconfigured_model_is_one_clear_503_with_cors_and_no_charge(hosted: Hosted) -> None:
    alice = hosted.account("alice@example.com")
    cid = with_evidence(alice.client)
    hosted.llm.script = [LLMMisconfigured(404)]
    before = len(hosted.llm.calls)
    r = alice.client.post(f"/cases/{cid}/start", headers={"Origin": WEB_ORIGIN})
    assert r.status_code == 503
    assert r.json()["misconfigured"] is True
    assert "misconfigured" in r.json()["detail"]
    assert r.headers["access-control-allow-origin"] == WEB_ORIGIN
    assert len(hosted.llm.calls) == before + 1  # one attempt, no retry loop
    assert alice.client.get("/me").json()["ai_calls_today"] == 0


def test_a_provider_5xx_is_a_503_that_never_repeats_its_body(hosted: Hosted) -> None:
    import httpx
    import openai

    req = httpx.Request("POST", "https://api.groq.test/openai/v1/chat/completions")
    secret = "provider echoed the prompt"
    alice = hosted.account("alice@example.com")
    cid = with_evidence(alice.client)
    hosted.llm.script = [
        openai.InternalServerError(secret, response=httpx.Response(500, request=req), body=None)
    ]
    r = alice.client.post(f"/cases/{cid}/start", headers={"Origin": WEB_ORIGIN})
    assert r.status_code == 503 and secret not in r.text
    assert r.headers["access-control-allow-origin"] == WEB_ORIGIN


def test_an_unexpected_error_is_a_500_the_browser_can_read(
    hosted: Hosted, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without CORS headers the browser sees a network failure and the app retried the POST."""
    from escalate.agent import runner

    def boom(_case_id: int) -> None:
        raise RuntimeError("secret detail")

    alice = hosted.account("alice@example.com")
    cid = with_evidence(alice.client)
    monkeypatch.setattr(runner, "start_case", boom)
    r = alice.client.post(f"/cases/{cid}/start", headers={"Origin": WEB_ORIGIN})
    assert r.status_code == 500 and "secret detail" not in r.text
    assert r.json()["error_id"]
    assert r.headers["access-control-allow-origin"] == WEB_ORIGIN


def test_the_tick_stops_at_a_misconfigured_model(
    hosted: Hosted, monkeypatch: pytest.MonkeyPatch
) -> None:
    from escalate.agent import runner
    from escalate.scheduler import tick

    tried: list[int] = []

    def fails(case_id: int, _step: str) -> None:
        tried.append(case_id)
        raise LLMMisconfigured(404)

    monkeypatch.setattr(tick, "due_cases", lambda: [(1, None), (2, None), (3, None)])
    monkeypatch.setattr(runner, "pending", lambda _c: {"type": "waiting_reply", "step": "s"})
    monkeypatch.setattr(runner, "resume_timeout", fails)
    monkeypatch.setattr(tick, "scan_deadlines", lambda: 0)
    assert tick.run_tick()["failed"] == 1
    assert tried == [1]


# --- M4: size, failures and evidence caps ---------------------------------------------------


def tokens_used(user: str) -> int:
    from escalate.db.models import AiUsage

    with session_scope() as s:
        row = s.get(AiUsage, (user, datetime.now().date()))
        return row.tokens if row else 0


def test_the_budget_counts_prompt_size_not_just_calls(
    hosted_db: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A 12M-character prompt cost one call. Now its estimated tokens count too."""
    from escalate.llm import set_llm
    from escalate.llm.quota import estimate_tokens
    from tests.fakes.fake_llm import FakeLLM

    monkeypatch.setenv("AI_TOKENS_PER_DAY", "20000")
    get_settings.cache_clear()
    set_llm(FakeLLM(handler=lambda p, s: "ok"))
    try:
        with as_user(A):
            assert get_llm().complete("x" * 40_000) == "ok"  # ~11k tokens
            assert tokens_used(A) == estimate_tokens("x" * 40_000)
            with pytest.raises(AiDailyLimit):
                get_llm().complete("x" * 40_000)
            assert get_llm().complete("small") == "ok"  # what's left still works
        assert used(A) == 2
    finally:
        set_llm(None)


def test_the_global_budget_is_token_aware(
    hosted_db: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GLOBAL_AI_TOKENS_PER_DAY", "5000")
    get_settings.cache_clear()
    charge(A, 4000)
    with pytest.raises(AiBusy):
        charge(B, 4000)
    assert tokens_used(GLOBAL_USAGE) == 4000 and tokens_used(B) == 0


def test_failed_calls_are_limited_per_user(
    hosted_db: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failures don't use up the call allowance, but after AI_FAILURES_PER_DAY of them the user
    can't hammer the provider any more today. Their tokens still count."""
    from escalate.llm import set_llm
    from escalate.llm.quota import AiFailureLimit
    from tests.fakes.fake_llm import FakeLLM

    monkeypatch.setenv("AI_FAILURES_PER_DAY", "3")
    get_settings.cache_clear()
    llm = FakeLLM(handler=lambda p, s: LLMBadOutput("x"))
    set_llm(llm)
    try:
        with as_user(A):
            for _ in range(3):
                with pytest.raises(LLMBadOutput):
                    get_llm().complete("ping")
            with pytest.raises(AiFailureLimit, match="paused until tomorrow"):
                get_llm().complete("ping")
        assert len(llm.calls) == 3  # the 4th never reached the provider
        assert used(A) == 0 and tokens_used(A) > 0
        with as_user(B), pytest.raises(LLMBadOutput):
            get_llm().complete("ping")  # other users are unaffected
    finally:
        set_llm(None)


def test_too_many_failures_is_a_friendly_429(
    hosted: Hosted, monkeypatch: pytest.MonkeyPatch
) -> None:
    from escalate.llm.quota import refund

    monkeypatch.setenv("AI_FAILURES_PER_DAY", "1")
    get_settings.cache_clear()
    acct = hosted.account("alice@example.com")
    with as_user(acct.id):
        refund(acct.id, charge(acct.id))
    cid = new_case(acct.client)
    acct.client.post(f"/cases/{cid}/evidence", files={"file": ("r.txt", b"BM-1", "text/plain")})
    r = acct.client.post(f"/cases/{cid}/start")
    assert r.status_code == 429 and r.json()["quota"] == "failures"


def test_evidence_text_in_a_prompt_is_capped_with_a_note(hosted: Hosted) -> None:
    from escalate.agent.intake import CUT_NOTE, evidence_blocks

    blocks = evidence_blocks([(1, "A" * 30_000), (2, "B" * 30_000), (3, "C" * 100)])
    assert blocks.count("A") == 30_000 and blocks.count("B") == 10_000
    assert CUT_NOTE in blocks and "evidence_id=3" not in blocks
    assert CUT_NOTE not in evidence_blocks([(1, "short")])


def test_a_huge_case_sends_a_bounded_prompt(hosted: Hosted) -> None:
    acct = hosted.account("alice@example.com")
    cid = new_case(acct.client)
    for i in range(10):
        body = f"BM-48213 file {i} ".encode() + b"z" * 400_000
        r = acct.client.post(
            f"/cases/{cid}/evidence", files={"file": (f"{i}.txt", body, "text/plain")}
        )
        assert r.status_code == 201, r.text
    acct.client.post(f"/cases/{cid}/start")
    assert hosted.llm.calls and max(len(p) for p, _ in hosted.llm.calls) < 60_000


def test_a_case_holds_at_most_max_evidence_files(hosted: Hosted) -> None:
    acct = hosted.account("alice@example.com")
    cid = new_case(acct.client)
    for i in range(10):
        r = acct.client.post(
            f"/cases/{cid}/evidence", files={"file": (f"{i}.txt", b"x", "text/plain")}
        )
        assert r.status_code == 201
    r = acct.client.post(f"/cases/{cid}/evidence", files={"file": ("11.txt", b"x", "text/plain")})
    assert r.status_code == 409 and "10 files" in r.json()["detail"]
