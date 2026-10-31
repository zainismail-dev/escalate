"""Evidence files: hashed, Fernet-encrypted at rest under EVIDENCE_DIR/<case_id>/<random>.bin.

The stored name is random (never derived from the upload's name, so no path traversal); the
user's filename is kept for display only. Paths are rebuilt from the case id and that random
name, and must resolve inside EVIDENCE_DIR (no symlinked folder out of it) before any read or
delete.

Hosted mode stores the same encrypted bytes in a private Supabase Storage bucket instead
(escalate/evidence/storage.py); the API's disk there is ephemeral.
"""

import hashlib
import os
import re
import secrets
import shutil
import unicodedata
from pathlib import Path

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.orm import Session

from escalate.config import Settings, get_settings
from escalate.db.events import log_event
from escalate.db.models import Case, Evidence
from escalate.evidence.ocr import ExtractResult, extract_text
from escalate.evidence.storage import Storage, SupabaseStorage
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


def _inside(base: str | Path, *parts: str) -> Path:
    """base/parts with symlinks resolved, if that stays strictly inside base; otherwise raise.
    Callers use only the returned path."""
    root = os.path.realpath(base)
    full = os.path.realpath(os.path.join(root, *parts))
    if not full.startswith(root + os.sep):
        raise UnsafeEvidencePath(f"{os.path.join(base, *parts)} is outside {base}")
    return Path(full)


def _case_id(case_id: int) -> str:
    if isinstance(case_id, bool) or not isinstance(case_id, int) or case_id < 0:
        raise UnsafeEvidencePath(f"not a case id: {case_id!r}")
    return str(case_id)


def case_dir(case_id: int, settings: Settings) -> Path:
    """EVIDENCE_DIR/<case_id>, built from the integer id only."""
    return _inside(settings.evidence_dir, _case_id(case_id))


def stored_path(evidence: Evidence, settings: Settings) -> Path:
    """Where an evidence file lives: its case folder plus its random stored name (the rest of
    the saved file_path is ignored)."""
    name = os.path.basename(evidence.file_path)
    if not STORED_NAME.fullmatch(name):
        raise UnsafeEvidencePath(f"evidence {evidence.id}: not a stored file name")
    return _inside(case_dir(evidence.case_id, settings), name)  # not another case's file


def kind_for(filename: str) -> str:
    return KINDS.get(Path(filename).suffix.lower(), "other")


def _fernet(settings: Settings) -> Fernet:
    if not settings.fernet_key:
        raise EvidenceKeyMissing(
            'FERNET_KEY is not set. Generate one with: python -c "from cryptography.fernet '
            'import Fernet; print(Fernet.generate_key().decode())"'
        )
    return Fernet(settings.fernet_key.encode())


class LocalStorage:
    """EVIDENCE_DIR/<case_id>/<random>.bin (local mode)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def put(self, case_id: int, user_id: str | None, blob: bytes) -> str:
        folder = case_dir(case_id, self.settings)
        folder.mkdir(parents=True, exist_ok=True)
        name = f"{secrets.token_hex(16)}.bin"
        _inside(folder, name).write_bytes(blob)
        return str(Path(self.settings.evidence_dir) / str(case_id) / name)  # reads use the name

    def get(self, file_path: str, case_id: int, user_id: str | None) -> bytes:
        ev = Evidence(case_id=case_id, file_path=file_path)
        return stored_path(ev, self.settings).read_bytes()

    def delete(self, file_paths: list[str], case_id: int, user_id: str | None) -> None:
        delete_files(case_id, self.settings)

    def delete_user(self, user_id: str) -> int:
        return 0  # local mode has no accounts


_storage_override: Storage | None = None


def set_storage(storage: Storage | None) -> None:
    """Tests swap in an in-memory store for hosted mode."""
    global _storage_override
    _storage_override = storage


def get_storage(settings: Settings | None = None) -> Storage:
    s = settings or get_settings()
    if not s.hosted:
        return LocalStorage(s)
    if _storage_override is not None:
        return _storage_override
    return SupabaseStorage(s.supabase_url, s.supabase_service_role_key, s.supabase_storage_bucket)


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
    owner = _owner(session, case_id) if s.hosted else None
    file_path = get_storage(s).put(case_id, owner, _fernet(s).encrypt(data))

    ev = Evidence(
        case_id=case_id,
        kind=kind_for(filename),
        filename=safe_filename(filename),
        file_path=file_path,
        sha256=sha,
        user_id=owner,
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


def _owner(session: Session, case_id: int) -> str | None:
    case = session.get(Case, case_id)
    return case.user_id if case is not None else None


def load_plain(evidence: Evidence, settings: Settings | None = None) -> bytes:
    s = settings or get_settings()
    if s.hosted:  # the caller has checked that this evidence row is the user's
        blob = get_storage(s).get(evidence.file_path, evidence.case_id, evidence.user_id)
        return _fernet(s).decrypt(blob)
    return _fernet(s).decrypt(stored_path(evidence, s).read_bytes())


def delete_case_files(session: Session, case_id: int, settings: Settings | None = None) -> None:
    """Every stored file of a case: its folder (local) or its objects (hosted)."""
    s = settings or get_settings()
    if not s.hosted:
        delete_files(case_id, s)
        return
    rows = session.execute(
        select(Evidence.file_path, Evidence.user_id).where(Evidence.case_id == case_id)
    ).all()
    for owner in {u for _, u in rows}:
        get_storage(s).delete([p for p, u in rows if u == owner], case_id, owner)


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
