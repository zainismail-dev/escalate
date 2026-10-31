"""Evidence files: hashed, Fernet-encrypted at rest under EVIDENCE_DIR/<case_id>/<random>.bin.

The stored name is random (never derived from the upload's name, so no path traversal); the
user's filename is kept for display only. Paths are rebuilt from the case id and that random
name, and must resolve inside EVIDENCE_DIR (no symlinked folder out of it) before any read or
delete.
"""

import hashlib
import re
import secrets
import shutil
import unicodedata
from pathlib import Path

from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from escalate.config import Settings, get_settings
from escalate.db.events import log_event
from escalate.db.models import Evidence
from escalate.evidence.ocr import ExtractResult, extract_text
from escalate.pii import mask_pii

KINDS = {
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
    ".gif": "image",
    ".tif": "image",
    ".tiff": "image",
    ".bmp": "image",
    ".pdf": "pdf",
    ".eml": "email",
    ".txt": "text",
    ".md": "text",
}


class EvidenceKeyMissing(RuntimeError):
    pass


class UnsafeEvidencePath(ValueError):
    """An evidence path that isn't a stored name inside EVIDENCE_DIR/<case_id>/."""


MAX_FILENAME = 120
STORED_NAME = re.compile(r"[0-9a-f]{32}\.bin")


def safe_filename(name: str) -> str:
    """The display name: no directories, no control characters, bounded length."""
    base = re.split(r"[\\/]", name or "")[-1]
    base = "".join(ch for ch in base if unicodedata.category(ch)[0] != "C").strip(" .")
    if len(base) > MAX_FILENAME:
        stem, suffix = Path(base).stem, Path(base).suffix[:10]
        base = stem[: MAX_FILENAME - len(suffix)] + suffix
    return base or "upload"


def _inside(base: Path, path: Path) -> Path:
    """`path`, if it resolves (symlinks followed) inside `base`; otherwise raise."""
    if not path.resolve().is_relative_to(base.resolve()):
        raise UnsafeEvidencePath(f"{path} is outside {base}")
    return path


def case_dir(case_id: int, settings: Settings) -> Path:
    """EVIDENCE_DIR/<case_id>, built from the integer id only."""
    if isinstance(case_id, bool) or not isinstance(case_id, int) or case_id < 0:
        raise UnsafeEvidencePath(f"not a case id: {case_id!r}")
    root = Path(settings.evidence_dir)
    return _inside(root, root / str(case_id))


def stored_path(evidence: Evidence, settings: Settings) -> Path:
    """Where an evidence file lives: its case folder plus its random stored name."""
    name = Path(evidence.file_path).name
    if not STORED_NAME.fullmatch(name):
        raise UnsafeEvidencePath(f"evidence {evidence.id}: not a stored file name")
    folder = case_dir(evidence.case_id, settings)
    return _inside(folder, folder / name)


def kind_for(filename: str) -> str:
    return KINDS.get(Path(filename).suffix.lower(), "other")


def _fernet(settings: Settings) -> Fernet:
    if not settings.fernet_key:
        raise EvidenceKeyMissing(
            'FERNET_KEY is not set. Generate one with: python -c "from cryptography.fernet '
            'import Fernet; print(Fernet.generate_key().decode())"'
        )
    return Fernet(settings.fernet_key.encode())


def save_upload(
    session: Session,
    case_id: int,
    filename: str,
    data: bytes,
    settings: Settings | None = None,
    extract: bool = True,
    result: ExtractResult | None = None,
) -> Evidence:
    """Encrypt and store an upload, extract its text, and log `evidence_added`."""
    s = settings or get_settings()
    sha = hashlib.sha256(data).hexdigest()
    folder = case_dir(case_id, s)
    folder.mkdir(parents=True, exist_ok=True)
    path = _inside(folder, folder / f"{secrets.token_hex(16)}.bin")
    path.write_bytes(_fernet(s).encrypt(data))

    ev = Evidence(
        case_id=case_id,
        kind=kind_for(filename),
        filename=safe_filename(filename),
        file_path=str(path),
        sha256=sha,
    )
    session.add(ev)
    session.flush()

    if extract:
        result = result or extract_text(ev, s, data=data)
        ev.extracted_text = mask_pii(result.text)
        ev.ocr_confidence = result.confidence
        ev.needs_review = result.needs_review

    log_event(
        session,
        case_id,
        "evidence_added",
        {
            "evidence_id": ev.id,
            "filename": ev.filename,
            "kind": ev.kind,
            "sha256": sha,
            "needs_review": ev.needs_review,
        },
    )
    return ev


def load_plain(evidence: Evidence, settings: Settings | None = None) -> bytes:
    s = settings or get_settings()
    return _fernet(s).decrypt(stored_path(evidence, s).read_bytes())


def delete_all_files(settings: Settings | None = None) -> None:
    """Delete-all: every case folder under EVIDENCE_DIR, including ones left by a crash."""
    root = Path((settings or get_settings()).evidence_dir)
    if root.is_dir():
        for folder in root.iterdir():
            if folder.is_dir() and folder.name.isdigit():
                shutil.rmtree(folder)


def delete_files(case_id: int, settings: Settings | None = None) -> None:
    """Remove every stored evidence file for a case."""
    folder = case_dir(case_id, settings or get_settings())
    if folder.is_dir():
        for f in folder.iterdir():
            f.unlink()  # a symlink inside is removed, never followed
        folder.rmdir()
