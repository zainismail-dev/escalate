"""Hosted-mode fixtures: DEPLOY_MODE=hosted with fake Supabase, JWKS, Groq and storage.

The database is a real Postgres when TEST_POSTGRES_URL is set (the CI "hosted" job), otherwise
a SQLite file in tmp_path. Either way, nothing here touches ./escalate.db or ./data.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import Engine, func, select
from sqlalchemy.schema import DropSchema

from escalate.config import get_settings
from escalate.db import session as db_session
from escalate.db.models import Base

PG_URL = os.environ.get("TEST_POSTGRES_URL", "")
SUPABASE_URL = "https://testproject.supabase.co"
WEB_ORIGIN = "https://beta.escalate.test"
API_HOST = "api.escalate.test"
TICK_SECRET = "t" * 48

HOSTED_ENV = {
    "DEPLOY_MODE": "hosted",
    "SUPABASE_URL": SUPABASE_URL,
    "SUPABASE_SERVICE_ROLE_KEY": "test-service-role-key",
    "LLM_BASE_URL": "https://api.groq.test/openai/v1",
    "LLM_API_KEY": "test-groq-key",
    "MODEL_SMART": "fake-smart",
    "MODEL_FAST": "fake-fast",
    "WEB_ORIGIN": WEB_ORIGIN,
    "ALLOWED_HOSTS": API_HOST,
    "TICK_SECRET": TICK_SECRET,
    "ALLOW_DEMO_SEED": "true",  # hosted mode must ignore it
    "API_DOCS": "true",  # hosted mode must ignore it
    "SMTP_USER": "owner@example.com",  # hosted mode must never use SMTP
    "SMTP_APP_PASSWORD": "app-pw",
}


@pytest.fixture
def hosted_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[dict[str, str]]:
    env = {
        **HOSTED_ENV,
        "FERNET_KEY": Fernet.generate_key().decode(),
        # Only the startup check reads this URL when there is no test Postgres: the engine is
        # bound by the `hosted_db` fixture.
        "DATABASE_URL": PG_URL or "postgresql://unused.invalid/escalate",
        "EVIDENCE_DIR": str(tmp_path / "evidence"),
        "CHECKPOINT_DB": str(tmp_path / "checkpoints.db"),
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    yield env
    get_settings.cache_clear()


def _reset_postgres(engine: Engine, schema: str) -> None:
    """A clean schema per test, built by the real migrations (so they run on Postgres too)."""
    from tests.hosted.migrate import upgrade

    with engine.begin() as conn:
        conn.execute(DropSchema(schema, cascade=True, if_exists=True))
    upgrade(PG_URL)


@pytest.fixture
def hosted_db(hosted_env: dict[str, str], tmp_path: Path) -> Iterator[Engine]:
    if PG_URL:
        engine = db_session.configure(PG_URL)
        _reset_postgres(engine, get_settings().db_schema)
    else:
        engine = db_session.configure(f"sqlite:///{tmp_path / 'hosted.db'}")
        Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


def count_rows(engine: Engine, table: str) -> int:
    t = Base.metadata.tables[table]
    with engine.connect() as conn:
        return int(conn.execute(select(func.count()).select_from(t)).scalar_one())
