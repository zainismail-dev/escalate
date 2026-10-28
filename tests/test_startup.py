"""API startup: fast, offline (no network, no LLM) and it keeps uvicorn's logging working."""

import asyncio
import logging
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from escalate.agent import runner
from escalate.api import main
from escalate.config import env_file_problems, get_settings
from escalate.db import session as db_session


@pytest.fixture
def startup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")
    monkeypatch.setenv("CHECKPOINT_DB", str(tmp_path / "checkpoints.db"))
    monkeypatch.setenv("EVIDENCE_DIR", str(tmp_path / "ev"))
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())
    # Unroutable address: if startup touched the LLM it would hang here, not return quickly.
    monkeypatch.setenv("LLM_BASE_URL", "http://10.255.255.1:11434/v1")
    get_settings.cache_clear()
    db_session.configure(f"sqlite:///{tmp_path / 'app.db'}")
    yield tmp_path
    runner.set_scheduler(None)
    get_settings.cache_clear()


async def _start_and_stop(app: object) -> float:
    t = time.monotonic()
    async with app.router.lifespan_context(app):  # type: ignore[attr-defined]
        elapsed = time.monotonic() - t
    return elapsed


def test_lifespan_startup_completes_quickly_and_offline(startup_env: Path) -> None:
    app = main.create_app()
    elapsed = asyncio.run(asyncio.wait_for(_start_and_stop(app), timeout=10))
    assert elapsed < 5, f"startup took {elapsed:.1f}s"
    assert (startup_env / "app.db").stat().st_size > 0  # migrations ran


def test_migrations_do_not_disable_uvicorn_loggers(startup_env: Path) -> None:
    """Alembic's fileConfig() used to disable every existing logger, so uvicorn never printed
    "Application startup complete" and the API looked hung."""
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).disabled = False
    main.init_db()
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        assert not logging.getLogger(name).disabled, name


def test_env_file_duplicates_are_reported_without_values(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("FERNET_KEY=secret-value\nA=1\n# FERNET_KEY=comment\nFERNET_KEY=\n")
    [problem] = env_file_problems(env)
    assert "FERNET_KEY is set 2 times" in problem and "lines 1, 4" in problem
    assert "secret-value" not in problem
    assert env_file_problems(tmp_path / "missing") == []


def test_startup_warns_about_empty_fernet_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FERNET_KEY", "")
    monkeypatch.chdir(Path(__file__).parent)  # no .env here
    get_settings.cache_clear()
    try:
        assert any("FERNET_KEY is empty" in w for w in main.startup_warnings())
    finally:
        get_settings.cache_clear()
