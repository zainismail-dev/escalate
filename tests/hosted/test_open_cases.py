"""L2: the open-case limit can't be bypassed: closed cases can't be started or continued, the
limit is checked and the case committed as one step, and reopening a resolved case counts."""

import threading
from pathlib import Path

import pytest

from escalate.db import repo
from tests.hosted.conftest import Hosted, hosted_mode
from tests.hosted.test_quota import new_case, with_evidence
from tests.hosted.test_sending import started


def test_a_withdrawn_case_cannot_be_started(hosted: Hosted) -> None:
    alice = hosted.account("alice@example.com")
    cid = with_evidence(alice.client)
    assert alice.client.post(f"/cases/{cid}/withdraw", json={}).status_code == 200
    r = alice.client.post(f"/cases/{cid}/start")
    assert r.status_code == 409 and "withdrawn" in r.json()["detail"]
    assert alice.client.post(f"/cases/{cid}/retry").status_code == 409
    assert alice.client.get(f"/cases/{cid}").json()["status"] == "withdrawn"


def test_a_withdrawn_case_with_a_pending_step_cannot_be_continued(hosted: Hosted) -> None:
    alice = hosted.account("alice@example.com")
    cid, draft = started(alice)
    assert alice.client.post(f"/cases/{cid}/withdraw", json={}).status_code == 200
    body = {"confirm": True, "recipient": draft["recipient"]}
    r = alice.client.post(f"/messages/{draft['message_id']}/approve", json=body)
    assert r.status_code == 409
    assert alice.client.get(f"/cases/{cid}").json()["status"] == "withdrawn"


def test_parallel_creates_cannot_both_take_the_last_slot(
    hosted: Hosted, monkeypatch: pytest.MonkeyPatch
) -> None:
    alice = hosted.account("alice@example.com")
    for n in range(2):
        new_case(alice.client, n)
    real = repo.open_case_count
    first_in, second_in = threading.Event(), threading.Event()
    seen: list[int] = []

    def slow_count(session: object) -> int:
        seen.append(1)
        if len(seen) == 1:
            first_in.set()
            second_in.wait(1.0)  # without the lock the other request counts meanwhile
        else:
            second_in.set()
        return real(session)  # type: ignore[arg-type]

    monkeypatch.setattr(repo, "open_case_count", slow_count)
    codes: list[int] = []

    def create(n: int) -> None:
        body = {"description": f"Broken LED TV, order BM-48213 #{n}", "country": "PK"}
        codes.append(alice.client.post("/cases", json=body).status_code)

    # The second request starts once the first is inside the limit check (the in-memory test
    # database is one connection: the two requests must not use it at the same moment).
    first = threading.Thread(target=create, args=(10,))
    first.start()
    assert first_in.wait(10)
    second = threading.Thread(target=create, args=(11,))
    second.start()
    for t in (first, second):
        t.join(20)
    monkeypatch.setattr(repo, "open_case_count", real)
    assert sorted(codes) == [201, 409]
    assert len(alice.client.get("/cases").json()) == 3


def test_reopening_a_resolved_case_respects_the_limit(tmp_path: Path) -> None:
    with hosted_mode(tmp_path, MAX_OPEN_CASES="2") as h:
        alice = h.account("alice@example.com")
        cid, draft = started(alice)
        mid = draft["message_id"]
        approve = {"confirm": True, "recipient": draft["recipient"]}
        assert alice.client.post(f"/messages/{mid}/approve", json=approve).status_code == 200
        assert alice.client.post(f"/messages/{mid}/confirm-delivery", json={}).status_code == 200
        alice.client.post(f"/cases/{cid}/replies", json={"text": "We refuse."})
        resolved = alice.client.post(f"/cases/{cid}/verdict", json={"verdict": "resolved"})
        assert resolved.status_code == 200, resolved.text
        new_case(alice.client, 1)
        new_case(alice.client, 2)  # two open cases again: the limit
        r = alice.client.post(f"/cases/{cid}/verdict", json={"verdict": "refused"})
        assert r.status_code == 409 and r.json()["quota"] == "open_cases"
        assert alice.client.get(f"/cases/{cid}").json()["status"] == "resolved"
