"""Third review M1: 4 parallel POST /messages/{id}/approve -> message_approved x4, one send,
then the extra resumes were taken as a "no reply" and the ladder jumped to the final notice.
The check, the approval and the resume now happen as one step under a per-case lock, and each
resume is tied to the message it approves."""

import contextlib
import threading

import pytest
from fastapi.testclient import TestClient
from freezegun import freeze_time

from escalate.agent import runner
from escalate.db.models import Case, Event
from tests.agent_env import AgentEnv, agent_env  # noqa: F401
from tests.fakes.fake_smtp import FakeSMTP
from tests.test_api import DAY0, _started, client, confirm_body  # noqa: F401

N = 4


def test_parallel_approves_send_once_and_wait_for_the_reply(
    client: TestClient,  # noqa: F811
    agent_env: AgentEnv,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with freeze_time(DAY0):
        cid = _started(client)
        mid = client.get(f"/cases/{cid}").json()["pending_draft"]["id"]
        body = confirm_body(client, mid)

    # Line every request up right after its "is this draft waiting for approval?" check, so
    # they all act on the same pause unless that check is serialised with the approval.
    barrier = threading.Barrier(N, timeout=2)
    real_expect = runner._expect

    def expect_then_wait(case_id: int, kind: str) -> dict:
        p = real_expect(case_id, kind)
        if kind == "approve_draft":
            # Serialised: the others are queued on the lock, so the barrier just times out.
            with contextlib.suppress(threading.BrokenBarrierError):
                barrier.wait()
        return p

    monkeypatch.setattr(runner, "_expect", expect_then_wait)
    codes: list[int] = []
    threads = [
        threading.Thread(
            target=lambda: codes.append(
                client.post(f"/messages/{mid}/approve", json=body).status_code
            )
        )
        for _ in range(N)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)

    assert sorted(codes) == [200] + [409] * (N - 1)
    assert len(FakeSMTP.all_sent()) == 1
    with agent_env.session() as s:
        case_pk = s.query(Case).filter_by(public_id=cid).one().id
        types = [e.type for e in s.query(Event).filter_by(case_id=case_pk).order_by(Event.id)]
    assert types.count("message_approved") == 1
    assert types.count("message_sent") == 1
    assert "reply_judged" not in types
    assert client.get(f"/cases/{cid}").json()["waiting_for"] == "waiting_reply"


def test_a_resume_for_another_message_is_refused(
    client: TestClient,  # noqa: F811
    agent_env: AgentEnv,  # noqa: F811
) -> None:
    with freeze_time(DAY0):
        cid = _started(client)
    with agent_env.session() as s:
        case_pk = s.query(Case).filter_by(public_id=cid).one().id
    with pytest.raises(runner.RunnerError, match="not the draft waiting"):
        runner.resume_with_decision(case_pk, "approve", message_id=987654)
    assert FakeSMTP.all_sent() == []
