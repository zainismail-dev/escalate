"""Hosted-mode fixtures: DEPLOY_MODE=hosted with fake Supabase (JWKS, Storage, admin API) and a
fake Groq (the FakeLLM). No network, no real accounts or secrets.

The database is a real Postgres when TEST_POSTGRES_URL is set (the CI "hosted" job), otherwise
a SQLite file in tmp_path. Either way, nothing here touches ./escalate.db or ./data.
"""

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jwt
import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.schema import DropSchema

import escalate.hosted.jwt as jwt_mod
from escalate.agent import runner
from escalate.config import get_settings
from escalate.db import session as db_session
from escalate.db.models import Base, Invite, User
from escalate.db.session import session_scope
from escalate.evidence.store import set_storage
from escalate.hosted.supabase_admin import set_admin
from escalate.llm import set_llm
from escalate.playbooks import loader
from escalate.safety import new_case_limiter
from tests.agent_env import make_llm
from tests.fakes.fake_llm import FakeLLM
from tests.fakes.memory_storage import FakeAdmin, MemoryStorage

PG_URL = os.environ.get("TEST_POSTGRES_URL", "")
SUPABASE_URL = "https://testproject.supabase.co"
ISSUER = f"{SUPABASE_URL}/auth/v1"
WEB_ORIGIN = "https://beta.escalate.test"
API_HOST = "api.escalate.test"
API_BASE = f"https://{API_HOST}"
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
    "APP_PASSCODE": "a passcode hosted mode must ignore",
    "SMTP_USER": "owner@example.com",  # hosted mode must never use SMTP
    "SMTP_APP_PASSWORD": "app-pw",
}


def hosted_environ(tmp: Path) -> dict[str, str]:
    return {
        **HOSTED_ENV,
        "FERNET_KEY": Fernet.generate_key().decode(),
        # Only the startup check reads this URL when there is no test Postgres: the engine is
        # bound to a SQLite file instead.
        "DATABASE_URL": PG_URL or "postgresql://unused.invalid/escalate",
        "EVIDENCE_DIR": str(tmp / "evidence"),
        "CHECKPOINT_DB": str(tmp / "checkpoints.db"),
    }


def bind_db(tmp: Path) -> Engine:
    if PG_URL:
        from tests.hosted.migrate import upgrade

        engine = db_session.configure(PG_URL)
        with engine.begin() as conn:  # a clean schema, built by the real migrations
            conn.execute(DropSchema(get_settings().db_schema, cascade=True, if_exists=True))
        upgrade(PG_URL)
        return engine
    # One shared in-memory connection, like the `db` fixture: a SQLite file allows one writer
    # at a time, and the AI quota is counted while a graph node's transaction is open (Postgres
    # locks rows, not the database, so that's fine there).
    engine = db_session.configure("sqlite://")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def hosted_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[dict[str, str]]:
    env = hosted_environ(tmp_path)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    yield env
    get_settings.cache_clear()


@pytest.fixture
def hosted_db(hosted_env: dict[str, str], tmp_path: Path) -> Iterator[Engine]:
    engine = bind_db(tmp_path)
    try:
        yield engine
    finally:
        engine.dispose()


def count_rows(engine: Engine, table: str) -> int:
    t = Base.metadata.tables[table]
    with engine.connect() as conn:
        return int(conn.execute(select(func.count()).select_from(t)).scalar_one())


# --- Supabase tokens --------------------------------------------------------------------------

DROP = object()  # a claim to leave out


@dataclass
class Signer:
    """A fake Supabase project signing key (ES256) and its JWKS."""

    key: ec.EllipticCurvePrivateKey = field(
        default_factory=lambda: ec.generate_private_key(ec.SECP256R1())
    )
    kid: str = field(default_factory=lambda: uuid.uuid4().hex)
    fetches: int = 0

    def jwk(self) -> dict[str, Any]:
        public = jwt.algorithms.ECAlgorithm.to_jwk(self.key.public_key(), as_dict=True)
        return {**public, "kid": self.kid, "alg": "ES256", "use": "sig"}

    def fetch(self, url: str) -> dict[str, Any]:
        assert url == f"{ISSUER}/.well-known/jwks.json"
        self.fetches += 1
        return {"keys": [self.jwk()]}

    def token(
        self,
        sub: str,
        email: str,
        *,
        alg: str = "ES256",
        key: Any = None,
        headers: dict[str, Any] | None = None,
        **claims: Any,
    ) -> str:
        now = int(datetime.now(UTC).timestamp())
        body: dict[str, Any] = {
            "iss": ISSUER,
            "aud": "authenticated",
            "sub": sub,
            "email": email,
            "role": "authenticated",
            "is_anonymous": False,
            "iat": now,
            "exp": now + 3600,
        }
        body.update(claims)
        body = {k: v for k, v in body.items() if v is not DROP}
        hdr = {"kid": self.kid, **(headers or {})}
        return jwt.encode(body, self.key if key is None else key, algorithm=alg, headers=hdr)


# --- a hosted app with users ------------------------------------------------------------------


@dataclass
class Account:
    id: str
    email: str
    client: TestClient


@dataclass
class Hosted:
    app: FastAPI
    engine: Engine
    signer: Signer
    storage: MemoryStorage
    admin: FakeAdmin
    llm: FakeLLM
    tmp: Path

    def client(self, token: str | None = None, **headers: str) -> TestClient:
        base = {"Origin": WEB_ORIGIN, "X-Escalate-Request": "1"}
        if token is not None:
            base["Authorization"] = f"Bearer {token}"
        return TestClient(self.app, base_url=API_BASE, headers={**base, **headers})

    def account(self, email: str, *, invited: bool = True, consented: bool = True) -> Account:
        uid = str(uuid.uuid4())
        with session_scope() as s:
            if invited:
                s.add(Invite(email=email))
            if invited and consented:
                s.add(User(id=uid, email=email, consented_at=datetime(2026, 1, 1)))
        return Account(uid, email, self.client(self.signer.token(uid, email)))


@contextmanager
def hosted_mode(tmp: Path, **env: str) -> Iterator[Hosted]:
    from escalate.api.main import create_app

    mp = pytest.MonkeyPatch()
    engine = None
    try:
        for k, v in {**hosted_environ(tmp), **env}.items():
            mp.setenv(k, v)
        get_settings.cache_clear()
        engine = bind_db(tmp)
        signer = Signer()
        mp.setattr(jwt_mod, "fetch_jwks", signer.fetch)
        storage, admin, llm = MemoryStorage(), FakeAdmin(), make_llm()
        set_storage(storage)
        set_admin(admin)
        set_llm(llm)
        loader.clear_cache()
        new_case_limiter.reset()
        runner.set_scheduler(None)
        runner.configure(None if PG_URL else tmp / "checkpoints.db")
        yield Hosted(create_app(startup=False), engine, signer, storage, admin, llm, tmp)
    finally:
        _close_checkpointer()
        set_storage(None)
        set_admin(None)
        set_llm(None)
        if engine is not None:
            engine.dispose()
        mp.undo()
        get_settings.cache_clear()


def _close_checkpointer() -> None:
    graph = runner._graph
    conn = getattr(graph.checkpointer, "conn", None) if graph is not None else None
    if conn is not None and hasattr(conn, "close"):
        conn.close()
    runner._graph = None  # the next test configures its own


@pytest.fixture
def hosted(tmp_path: Path) -> Iterator[Hosted]:
    with hosted_mode(tmp_path) as h:
        yield h
