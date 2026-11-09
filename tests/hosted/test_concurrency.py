"""M3: one user's slow AI call never blocks another user's case, the worker threads or /health.

Only the per-case lock serialises agent runs in hosted mode; a bounded number of agent slots
keeps a slow provider from tying up every worker thread."""

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from escalate.agent import runner
from escalate.llm import set_llm
from escalate.llm.client import Slot
from tests.factories import LED_TEXT
from tests.fakes.fake_llm import FakeLLM
from tests.hosted.conftest import Account, Hosted, hosted_mode

SLOW = "SLOW-CASE-7781"


class SlowLLM:
    """The test FakeLLM, except that prompts about the slow case wait until released."""

    def __init__(self, inner: FakeLLM) -> None:
        self.inner = inner
        self.entered = threading.Event()
        self.release = threading.Event()

    def complete(self, prompt: str, slot: Slot = "smart", json_mode: bool = False) -> str:
        if SLOW in prompt:
            self.entered.set()
            assert self.release.wait(30), "the slow call was never released"
        return self.inner.complete(prompt, slot, json_mode)


def _case(acct: Account, evidence: bytes) -> str:
    c = acct.client
    cid: str = c.post("/cases", json={"description": LED_TEXT, "country": "PK"}).json()["id"]
    r = c.post(f"/cases/{cid}/evidence", files={"file": ("r.txt", evidence, "text/plain")})
    assert r.status_code == 201, r.text
    return cid


@pytest.fixture
def slow(hosted: Hosted) -> Iterator[SlowLLM]:
    llm = SlowLLM(hosted.llm)
    set_llm(llm)
    runner.reset_slots()
    yield llm
    llm.release.set()
    runner.reset_slots()


def _start_in_thread(acct: Account, cid: str, out: dict[str, int]) -> threading.Thread:
    def go() -> None:
        out[cid] = acct.client.post(f"/cases/{cid}/start").status_code

    t = threading.Thread(target=go, daemon=True)
    t.start()
    return t


def test_user_b_is_not_blocked_by_user_a_s_slow_ai_call(hosted: Hosted, slow: SlowLLM) -> None:
    alice, bob = hosted.account("alice@example.com"), hosted.account("bob@example.com")
    a_case = _case(alice, f"BM-48213 {SLOW}".encode())
    b_case = _case(bob, b"BM-48213")
    status: dict[str, int] = {}
    a = _start_in_thread(alice, a_case, status)
    try:
        assert slow.entered.wait(15), "alice's run never reached the AI"
        b = _start_in_thread(bob, b_case, status)
        b.join(20)
        assert not b.is_alive(), "bob's /start waited for alice's AI call"
        assert status[b_case] == 200
        assert hosted.client().get("/health").json() == {"ok": True}
        assert a.is_alive()  # alice is still waiting on the AI
    finally:
        slow.release.set()
        a.join(20)
    assert status[a_case] == 200


def test_when_every_agent_slot_is_busy_the_next_run_is_a_quick_503(tmp_path: Path) -> None:
    with hosted_mode(tmp_path, AGENT_CONCURRENCY="1", AGENT_SLOT_WAIT_S="0.1") as h:
        llm = SlowLLM(h.llm)
        set_llm(llm)
        runner.reset_slots()
        try:
            alice, bob = h.account("alice@example.com"), h.account("bob@example.com")
            a_case = _case(alice, f"BM-48213 {SLOW}".encode())
            b_case = _case(bob, b"BM-48213")
            status: dict[str, int] = {}
            a = _start_in_thread(alice, a_case, status)
            assert llm.entered.wait(15)
            r = bob.client.post(f"/cases/{b_case}/start")
            assert r.status_code == 503 and r.json()["busy"] is True
            llm.release.set()
            a.join(20)
            assert status[a_case] == 200
            assert bob.client.post(f"/cases/{b_case}/start").status_code == 200  # free again
        finally:
            llm.release.set()
            runner.reset_slots()
