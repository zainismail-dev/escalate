from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from escalate.config import Settings
from escalate.db import session as db_session
from escalate.db.models import Base


@pytest.fixture
def db() -> Iterator[Session]:
    """A fresh in-memory SQLite database, bound as the global engine."""
    engine = db_session.configure("sqlite://")
    Base.metadata.create_all(engine)
    s = db_session.session_factory()()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings isolated to a temp folder, with a fresh Fernet key and fake model names."""
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        evidence_dir=tmp_path / "evidence",
        fernet_key=Fernet.generate_key().decode(),
        model_smart="fake-smart",
        model_fast="fake-fast",
        checkpoint_db=tmp_path / "checkpoints.db",
    )
