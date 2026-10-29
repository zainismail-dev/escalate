"""Evidence uploads: size, magic bytes, executables, archives, bombs, names, traversal."""

import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from escalate.evidence.ocr import MAX_IMAGE_PIXELS
from escalate.evidence.sniff import UploadRejected, check_upload
from escalate.evidence.store import safe_filename
from tests.agent_env import AgentEnv, agent_env  # noqa: F401
from tests.test_api import _create, client  # noqa: F401

FIX = Path(__file__).parents[1] / "fixtures"


def _png(width: int, height: int) -> bytes:
    buf = io.BytesIO()
    Image.new("1", (width, height)).save(buf, "PNG")  # 1-bit: a huge canvas compresses to bytes
    return buf.getvalue()


def _zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("receipt.txt", "x")
    return buf.getvalue()


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("receipt.png", (FIX / "receipt.png").read_bytes()),
        ("receipt.pdf", (FIX / "receipt.pdf").read_bytes()),
        ("reply.eml", (FIX / "seller_reply.eml").read_bytes()),
        ("notes.txt", "Paid ₨ 45,000 — order BM-48213".encode()),
        ("photo.JPG", b"\xff\xd8\xff\xe0" + b"\x00" * 64),
    ],
)
def test_real_evidence_is_accepted(name: str, data: bytes) -> None:
    if name.endswith(".JPG"):  # a header-only JPEG is unreadable: build a real one
        buf = io.BytesIO()
        Image.new("RGB", (8, 8)).save(buf, "JPEG")
        data = buf.getvalue()
    assert check_upload(name, data) in {"image", "pdf", "email", "text"}


@pytest.mark.parametrize(
    ("name", "data", "why"),
    [
        ("receipt.png", b"MZ\x90\x00" + b"\x00" * 64, "Windows program"),
        ("receipt.pdf", b"\x7fELF\x02\x01\x01" + b"\x00" * 64, "Linux program"),
        ("notes.txt", b"#!/bin/sh\nrm -rf ~\n", "script"),
        ("receipt.png", _zip(), "zip archive"),
        ("evidence.pdf", b"\x1f\x8b\x08\x00" + b"\x00" * 64, "gzip archive"),
        ("receipt.pdf", b"Rar!\x1a\x07\x00", "RAR archive"),
        ("invoice.png", b"%PDF-1.7\n", "not a PNG"),
        ("invoice.pdf", (FIX / "receipt.png").read_bytes(), "not a PDF"),
        ("notes.txt", b"plain\x00binary", "binary data"),
        ("notes.txt", b"\xff\xfe\xfa caf\xe9", "not UTF-8"),
        ("payload.exe", b"hello", "unsupported file type"),
        ("archive.zip", b"hello", "unsupported file type"),
        ("page.html", b"<script>alert(1)</script>", "unsupported file type"),
        ("image.svg", b"<svg onload=alert(1)>", "unsupported file type"),
    ],
)
def test_dangerous_or_mislabelled_files_are_refused(name: str, data: bytes, why: str) -> None:
    with pytest.raises(UploadRejected, match=why):
        check_upload(name, data)


def test_tar_archives_are_refused() -> None:
    data = bytearray(1024)
    data[257:262] = b"ustar"
    with pytest.raises(UploadRejected, match="tar archive"):
        check_upload("notes.txt", bytes(data))


def test_decompression_bomb_image_is_refused_before_ocr() -> None:
    side = int(MAX_IMAGE_PIXELS**0.5) + 100
    bomb = _png(side, side)
    assert len(bomb) < 2_000_000  # small on disk, huge in memory
    with pytest.raises(UploadRejected, match="too large"):
        check_upload("screenshot.png", bomb)


@pytest.mark.parametrize(
    ("raw", "safe"),
    [
        ("../../etc/passwd", "passwd"),
        ("..\\..\\windows\\system32\\x.png", "x.png"),
        ("/abs/path/receipt.pdf", "receipt.pdf"),
        ("rec\x00eipt\r\n.png", "receipt.png"),
        ("..", "upload"),
        ("", "upload"),
        ("a" * 300 + ".pdf", "a" * 116 + ".pdf"),
    ],
)
def test_filenames_are_display_only_and_safe(raw: str, safe: str) -> None:
    assert safe_filename(raw) == safe


def test_upload_endpoint_refuses_and_stores_safely(
    client: TestClient,  # noqa: F811
    tmp_path: Path,
) -> None:
    cid = _create(client)["id"]
    bad = client.post(f"/cases/{cid}/evidence", files={"file": ("x.png", b"MZ" + b"\0" * 99)})
    assert bad.status_code == 415
    assert "Windows program" in bad.json()["detail"]

    good = client.post(
        f"/cases/{cid}/evidence",
        files={"file": ("../../../../tmp/owned.txt", b"Order BM-48213", "text/plain")},
    )
    assert good.status_code == 201
    assert good.json()["filename"] == "owned.txt"
    stored = list((tmp_path / "ev").rglob("*.bin"))
    assert len(stored) == 1 and stored[0].is_relative_to(tmp_path / "ev")
    assert "owned" not in stored[0].name
    assert not Path("/tmp/owned.txt").exists()


def test_oversized_upload_is_refused(
    client: TestClient,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from escalate.config import get_settings

    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    get_settings.cache_clear()
    cid = _create(client)["id"]
    big = b"a" * (1024 * 1024 + 10)
    r = client.post(f"/cases/{cid}/evidence", files={"file": ("big.txt", big, "text/plain")})
    assert r.status_code == 413
