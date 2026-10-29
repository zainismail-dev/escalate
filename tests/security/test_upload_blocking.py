"""Second review N7: OCR and PDF parsing ran on the API's event loop, so one large upload
froze every other request (even /health) until Tesseract finished."""

import threading
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from escalate.config import get_settings
from escalate.evidence import ocr, store
from tests.agent_env import AgentEnv, agent_env  # noqa: F401
from tests.test_api import _create, client  # noqa: F401


@pytest.fixture
def held_ocr(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[threading.Event, threading.Event]]:
    """Text extraction that starts, then waits until the test releases it."""
    started, release = threading.Event(), threading.Event()

    def slow(*_args: object, **_kw: object) -> ocr.ExtractResult:
        started.set()
        release.wait(30)
        return ocr.ExtractResult("Order BM-48213")

    monkeypatch.setattr(ocr, "extract_bytes", slow, raising=False)
    monkeypatch.setattr(store, "extract_text", slow)  # the old code path
    yield started, release
    release.set()


def _upload(c: TestClient, cid: str, out: list[int]) -> None:
    files = {"file": ("receipt.txt", b"Order BM-48213, PKR 45000", "text/plain")}
    out.append(c.post(f"/cases/{cid}/evidence", files=files).status_code)


def test_health_answers_while_an_upload_is_being_read(
    client: TestClient,  # noqa: F811
    held_ocr: tuple[threading.Event, threading.Event],
) -> None:
    started, release = held_ocr
    cid = _create(client)["id"]
    upload: list[int] = []
    t = threading.Thread(target=_upload, args=(client, cid, upload))
    t.start()
    assert started.wait(10), "extraction never started"

    health: list[int] = []
    h = threading.Thread(target=lambda: health.append(client.get("/health").status_code))
    h.start()
    h.join(5)
    responsive = not h.is_alive()
    release.set()
    t.join(30)
    h.join(30)
    assert responsive, "/health was blocked by OCR running on the event loop"
    assert health == [200] and upload == [201]


def test_slow_extraction_times_out_and_marks_the_file_for_review(
    client: TestClient,  # noqa: F811
    held_ocr: tuple[threading.Event, threading.Event],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OCR_TIMEOUT_S", "1")
    get_settings.cache_clear()
    cid = _create(client)["id"]
    files = {"file": ("receipt.txt", b"Order BM-48213", "text/plain")}
    r = client.post(f"/cases/{cid}/evidence", files=files)  # never released: times out
    assert r.status_code == 201
    assert r.json()["needs_review"] is True
