import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import freezegun
import pytest
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from escalate.config import Settings
from escalate.db import session as db_session
from escalate.db.models import Base

# Never read the developer's .env either (e.g. DEMO_MODE=true there would change test results).
Settings.model_config["env_file"] = None

# Tests pick their mode: local unless a test (tests/hosted) switches to hosted itself. The CI
# "hosted" job sets DEPLOY_MODE=hosted for its own steps; it must not change the local tests.
os.environ.pop("DEPLOY_MODE", None)

# Never read a developer's saved web settings (data/settings.json) in tests.
os.environ["ESCALATE_SETTINGS_FILE"] = os.devnull

# Never touch the developer's ./escalate.db or ./data: a test that forgets the `db` fixture
# gets an empty in-memory database (and fails loudly) instead.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["CHECKPOINT_DB"] = os.path.join(tempfile.mkdtemp(prefix="escalate-tests-"), "cp.db")
# ...nor ./data/evidence: delete-all and case deletion remove folders named by case id, and the
# in-memory test cases reuse ids 1, 2, 3...
os.environ["EVIDENCE_DIR"] = tempfile.mkdtemp(prefix="escalate-tests-evidence-")

# pandas (pulled in by pytesseract) crashes if first imported while time is frozen.
freezegun.configure(extend_ignore_list=["pandas", "pytesseract"])


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
