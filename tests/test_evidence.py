import hashlib
import re
import shutil
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session

from escalate.config import Settings
from escalate.db.models import Case
from escalate.evidence import ocr
from escalate.evidence.store import EvidenceKeyMissing, kind_for, load_plain, save_upload

FIX = Path(__file__).parent / "fixtures"
HAS_TESSERACT = shutil.which("tesseract") is not None


@pytest.fixture
def case(db: Session) -> Case:
    c = Case(description="LED broke")
    db.add(c)
    db.flush()
    return c


def test_upload_is_encrypted_hashed_and_logged(db: Session, case: Case, settings: Settings) -> None:
    data = (FIX / "seller_reply.eml").read_bytes()
    ev = save_upload(db, case.id, "seller_reply.eml", data, settings)

    sha = hashlib.sha256(data).hexdigest()
    assert ev.sha256 == sha
    # Stored under a random name in the case's folder: not the hash, not the user's filename.
    stored = Path(ev.file_path)
    assert stored.parent == settings.evidence_dir / str(case.id)
    assert re.fullmatch(r"[0-9a-f]{32}\.bin", stored.name)
    on_disk = Path(ev.file_path).read_bytes()
    assert b"claim is approved" not in on_disk
    assert b"BM-48213" not in on_disk
    assert load_plain(ev, settings) == data

    db.refresh(case)
    assert [e.type for e in case.events] == ["evidence_added"]
    assert case.events[0].payload["sha256"] == sha


def test_eml_text(db: Session, case: Case, settings: Settings) -> None:
    ev = save_upload(db, case.id, "r.eml", (FIX / "seller_reply.eml").read_bytes(), settings)
    assert ev.kind == "email"
    assert "Subject: Re: Order BM-48213" in (ev.extracted_text or "")
    assert "when the company claim is approved" in (ev.extracted_text or "")
    assert ev.needs_review is False


def test_pdf_text(db: Session, case: Case, settings: Settings) -> None:
    ev = save_upload(db, case.id, "receipt.pdf", (FIX / "receipt.pdf").read_bytes(), settings)
    assert "Order ID: BM-48213" in (ev.extracted_text or "")
    assert ev.needs_review is False


def test_txt_text(db: Session, case: Case, settings: Settings) -> None:
    ev = save_upload(db, case.id, "notes.txt", b"Paid 45000 on 2026-02-14", settings)
    assert ev.extracted_text == "Paid 45000 on 2026-02-14"


def test_missing_key_is_refused(db: Session, case: Case, settings: Settings) -> None:
    with pytest.raises(EvidenceKeyMissing):
        save_upload(db, case.id, "a.txt", b"x", settings.model_copy(update={"fernet_key": ""}))


def test_kind_for() -> None:
    assert kind_for("A.JPG") == "image"
    assert kind_for("x.pdf") == "pdf"
    assert kind_for("x.zip") == "other"


def _fake_data(confs: list[float]) -> dict[str, Any]:
    n = len(confs)
    return {
        "text": [f"w{i}" for i in range(n)],
        "conf": confs,
        "block_num": [1] * n,
        "par_num": [1] * n,
        "line_num": list(range(n)),
    }


@pytest.mark.parametrize(("confs", "review"), [([90.0, 80.0], False), ([50.0, 40.0], True)])
def test_low_ocr_confidence_needs_review(
    monkeypatch: pytest.MonkeyPatch, confs: list[float], review: bool
) -> None:
    import pytesseract

    seen: dict[str, Any] = {}

    def fake_image_to_data(img: Any, lang: str, output_type: Any) -> dict[str, Any]:
        seen["lang"] = lang
        return _fake_data(confs)

    monkeypatch.setattr(pytesseract, "image_to_data", fake_image_to_data)
    result = ocr._image((FIX / "receipt.png").read_bytes(), "eng+urd")
    assert result.needs_review is review
    assert result.confidence == sum(confs) / len(confs)
    assert seen["lang"] == "eng+urd"


def test_missing_tesseract_flags_review(monkeypatch: pytest.MonkeyPatch) -> None:
    import pytesseract

    def boom(*a: Any, **k: Any) -> None:
        raise pytesseract.TesseractNotFoundError()

    monkeypatch.setattr(pytesseract, "image_to_data", boom)
    result = ocr._image((FIX / "receipt.png").read_bytes(), "eng")
    assert result.needs_review is True and result.text == ""


@pytest.mark.skipif(not HAS_TESSERACT, reason="tesseract binary not installed")
def test_real_ocr_reads_fixture_receipt(db: Session, case: Case, settings: Settings) -> None:
    ev = save_upload(db, case.id, "receipt.png", (FIX / "receipt.png").read_bytes(), settings)
    text = ev.extracted_text or ""
    assert "BM-48213" in text
    assert "45000" in text
    assert ev.needs_review is False
