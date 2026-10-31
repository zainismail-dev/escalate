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
from escalate.llm.quota import AiBusy, AiDailyLimit, calls_today, charge
from tests.factories import LED_TEXT
from tests.hosted.conftest import Hosted

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
