"""POST /internal/tick: a secret header (constant-time compare, 404 otherwise), runs every user's
due wake-ups as that user, and is idempotent."""

from datetime import datetime, timedelta

from freezegun import freeze_time
from sqlalchemy import select

from escalate.db.models import GLOBAL_USAGE, Case, Event
from escalate.db.session import session_scope
from escalate.llm.quota import calls_today
from tests.fakes.memory_storage import FakeAdmin  # noqa: F401  (fixtures share the module)
from tests.hosted.conftest import TICK_SECRET, Account, Hosted
from tests.hosted.test_sending import started

DAY0 = datetime(2026, 10, 1, 9)


def tick(hosted: Hosted, secret: str | None = TICK_SECRET, **headers: str):  # type: ignore[no-untyped-def]
    h = {"X-Tick-Secret": secret} if secret is not None else {}
    # GitHub Actions sends no Origin, no CSRF header and no token
    return hosted.client(**h, **headers).post(
        "/internal/tick", headers={"Origin": "", "X-Escalate-Request": ""}
    )


def test_a_missing_or_wrong_secret_is_a_plain_404(hosted: Hosted) -> None:
    for secret in (None, "", "t" * 47, "t" * 49, "T" * 48, TICK_SECRET[:-1] + "u"):
        r = tick(hosted, secret)
        assert r.status_code == 404 and r.json() == {"detail": "Not Found"}, secret
    assert tick(hosted).status_code == 200


def test_a_user_token_is_not_a_tick_secret(hosted: Hosted) -> None:
    alice = hosted.account("alice@example.com")
    r = alice.client.post("/internal/tick")
    assert r.status_code == 404


def waiting_case(hosted: Hosted, email: str) -> tuple[Account, str]:
    acct = hosted.account(email)
    cid, draft = started(acct)
    acct.client.post(
        f"/messages/{draft['message_id']}/approve",
        json={"confirm": True, "recipient": draft["recipient"]},
    )
    r = acct.client.post(
        f"/messages/{draft['message_id']}/confirm-delivery", json={"evidence_id": None}
    )
    assert r.json()["waiting_for"] == "waiting_reply"
    return acct, cid


def usage(user: str) -> int:
    with session_scope() as s:
        return calls_today(s, user)


def test_due_wake_ups_run_as_their_owner_once(hosted: Hosted) -> None:
    with freeze_time(DAY0):
        alice, a_case = waiting_case(hosted, "alice@example.com")
        bob, b_case = waiting_case(hosted, "bob@example.com")
        assert tick(hosted).json()["woke"] == 0  # nothing due yet
    with session_scope() as s:
        due = s.scalar(select(Case.next_action_at).where(Case.public_id == a_case))
    assert due is not None
    with freeze_time(due + timedelta(hours=1)):
        model_calls = len(hosted.llm.calls)
        first = tick(hosted).json()
        assert first["woke"] == 2 and first["failed"] == 0
        assert tick(hosted).json()["woke"] == 0  # idempotent
        # every model call the tick made was charged to the owner of the case it ran for
        made = len(hosted.llm.calls) - model_calls
        assert usage(alice.id) + usage(bob.id) == usage(GLOBAL_USAGE) == made
    with session_scope() as s:
        for acct, cid in ((alice, a_case), (bob, b_case)):
            case = s.scalar(select(Case).where(Case.public_id == cid))
            assert case is not None and case.status != "waiting_reply"
            expired = s.scalars(
                select(Event.user_id).where(Event.case_id == case.id, Event.type == "wait_expired")
            ).all()
            assert expired == [acct.id]


def test_a_user_out_of_ai_calls_is_skipped_until_the_next_tick(
    hosted: Hosted, monkeypatch: object
) -> None:
    import pytest

    mp: pytest.MonkeyPatch = monkeypatch  # type: ignore[assignment]
    with freeze_time(DAY0):
        _alice, cid = waiting_case(hosted, "alice@example.com")
    with session_scope() as s:
        due = s.scalar(select(Case.next_action_at).where(Case.public_id == cid))
    assert due is not None
    from escalate.config import get_settings

    with freeze_time(due + timedelta(hours=1)):
        mp.setenv("AI_CALLS_PER_DAY", "3")
        get_settings.cache_clear()
        assert tick(hosted).json() == {"woke": 0, "skipped": 1, "failed": 0, "deadline_warnings": 0}
        mp.setenv("AI_CALLS_PER_DAY", "40")
        get_settings.cache_clear()
        assert tick(hosted).json()["woke"] == 1
