"""M5: hosted uploads and downloads are bounded per user: file size, total storage, files per
case, one upload at a time, no database connection held during OCR, and rate-limited PDFs and
exports."""

import threading
from pathlib import Path

import pytest
from sqlalchemy import event

from escalate.config import get_settings
from escalate.evidence import ocr
from escalate.evidence.ocr import ExtractResult
from tests.hosted.conftest import Account, Hosted, hosted_mode
from tests.hosted.test_quota import new_case


def upload(acct: Account, cid: str, data: bytes, name: str = "r.txt") -> int:
    files = {"file": (name, data, "text/plain")}
    return acct.client.post(f"/cases/{cid}/evidence", files=files).status_code


def test_hosted_files_are_limited_to_10_mb_by_default(hosted: Hosted) -> None:
    assert get_settings().upload_limit_mb == 10
    acct = hosted.account("alice@example.com")
    cid = new_case(acct.client)
    assert upload(acct, cid, b"x" * (10 * 1024 * 1024 + 1)) == 413


def test_each_user_has_a_storage_cap(tmp_path: Path) -> None:
    with hosted_mode(tmp_path, MAX_STORAGE_MB_PER_USER="1") as h:
        alice, bob = h.account("alice@example.com"), h.account("bob@example.com")
        a1, a2 = new_case(alice.client, 1), new_case(alice.client, 2)
        assert upload(alice, a1, b"x" * 600_000) == 201
        r = alice.client.post(
            f"/cases/{a2}/evidence", files={"file": ("r.txt", b"y" * 600_000, "text/plain")}
        )
        assert r.status_code == 413 and "1 MB" in r.json()["detail"]  # across cases
        assert upload(bob, new_case(bob.client), b"z" * 600_000) == 201  # bob is unaffected


def test_one_upload_at_a_time_per_user_and_no_db_connection_during_ocr(
    hosted: Hosted, monkeypatch: pytest.MonkeyPatch
) -> None:
    alice, bob = hosted.account("alice@example.com"), hosted.account("bob@example.com")
    a_case, b_case = new_case(alice.client, 1), new_case(bob.client, 2)
    entered, release = threading.Event(), threading.Event()
    held: list[int] = []
    out = {"n": 0}

    @event.listens_for(hosted.engine, "checkout")
    def _out(*_a: object) -> None:
        out["n"] += 1

    @event.listens_for(hosted.engine, "checkin")
    def _in(*_a: object) -> None:
        out["n"] -= 1

    def slow_extract(kind: str, data: bytes, *a: object, **k: object) -> ExtractResult:
        if b"SLOW" in data:
            held.append(out["n"])
            entered.set()
            assert release.wait(20)
        return ExtractResult(data.decode(errors="ignore"))

    monkeypatch.setattr(ocr, "extract_bytes", slow_extract)
    status: dict[str, int] = {}
    t = threading.Thread(target=lambda: status.update(a=upload(alice, a_case, b"SLOW BM-1")))
    t.start()
    try:
        assert entered.wait(15)
        r = alice.client.post(
            f"/cases/{a_case}/evidence", files={"file": ("2.txt", b"BM-2", "text/plain")}
        )
        assert r.status_code == 409 and "upload in progress" in r.json()["detail"]
        assert upload(bob, b_case, b"BM-3") == 201  # other users can upload meanwhile
    finally:
        release.set()
        t.join(20)
        event.remove(hosted.engine, "checkout", _out)
        event.remove(hosted.engine, "checkin", _in)
    assert status["a"] == 201
    assert held == [0], "a database connection was checked out during OCR"
    assert upload(alice, a_case, b"BM-4") == 201  # free again


def test_pdf_and_export_downloads_are_rate_limited_per_user(tmp_path: Path) -> None:
    with hosted_mode(tmp_path, RATE_LIMIT_DOWNLOADS_PER_MINUTE="2") as h:
        alice, bob = h.account("alice@example.com"), h.account("bob@example.com")
        cid = new_case(alice.client)
        codes = [alice.client.get("/me/export").status_code for _ in range(2)]
        assert codes == [200, 200]
        r = alice.client.get(f"/cases/{cid}/export.pdf")
        assert r.status_code == 429 and r.headers["retry-after"] == "60"
        assert bob.client.get("/me/export").status_code == 200
        assert alice.client.get(f"/cases/{cid}").status_code == 200  # other GETs are not
