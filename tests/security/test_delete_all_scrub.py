"""Second review N4: after delete-all, `strings` on the database, its WAL and the LangGraph
checkpoint file still found the demo cases' text (free pages, WAL, old checkpoints)."""

from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from escalate.agent import runner
from escalate.api.main import create_app
from escalate.config import get_settings
from escalate.db import session as db_session
from tests.factories import APP_BASE_URL, APP_HEADERS

# Text that only the four demo cases contain (descriptions, facts, extracted evidence, drafts).
MARKERS = [b"BrightMart", b"PulseFit", b"Northline", b"BM-48213"]


def _disk(tmp: Path) -> bytes:
    """Every byte the app keeps on disk for these cases: DBs, WAL/journal files, evidence."""
    return b"".join(p.read_bytes() for p in tmp.rglob("*") if p.is_file())


def test_delete_all_leaves_no_case_text_on_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{data / 'escalate.db'}")  # a scratch DB
    monkeypatch.setenv("CHECKPOINT_DB", str(data / "checkpoints.db"))
    monkeypatch.setenv("EVIDENCE_DIR", str(data / "evidence"))
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("ALLOW_DEMO_SEED", "true")
    get_settings.cache_clear()
    db_session.configure()
    try:
        with TestClient(create_app(), base_url=APP_BASE_URL, headers=APP_HEADERS) as c:
            assert c.post("/demo/seed").status_code == 201
            before = _disk(data)
            assert all(m in before for m in MARKERS)  # the attack's precondition

            assert c.post("/privacy/delete-all", json={"confirm": True}).status_code == 204
            assert c.get("/cases").json() == []
            after = _disk(data)
    finally:
        db_session.configure("sqlite://")
        runner.configure(tmp_path / "unused-cp.db")
        get_settings.cache_clear()
    leaked = [m.decode() for m in MARKERS if m in after]
    assert leaked == [], f"case text still on disk after delete-all: {leaked}"
    assert not any((data / "evidence").rglob("*.bin"))


def test_delete_all_works_on_a_fresh_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No case has ever run, so LangGraph has not created its tables yet (CI caught a 500)."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'escalate.db'}")
    monkeypatch.setenv("CHECKPOINT_DB", str(tmp_path / "checkpoints.db"))
    monkeypatch.setenv("EVIDENCE_DIR", str(tmp_path / "evidence"))
    get_settings.cache_clear()
    db_session.configure()
    try:
        with TestClient(create_app(), base_url=APP_BASE_URL, headers=APP_HEADERS) as c:
            assert c.post("/privacy/delete-all", json={"confirm": True}).status_code == 204
    finally:
        db_session.configure("sqlite://")
        runner.configure(tmp_path / "unused-cp.db")
        get_settings.cache_clear()
