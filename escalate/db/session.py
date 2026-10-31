"""Engine and session factory built from DATABASE_URL."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

import escalate.db.tenancy  # noqa: F401  (registers the per-user query filter)
from escalate.config import get_settings

_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None


def sqlalchemy_url(url: str) -> str:
    """Supabase shows `postgresql://...`: use the psycopg 3 driver for it."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url.removeprefix(prefix)
    return url


def pg_schema(url: str) -> str | None:
    """Hosted Postgres keeps every table in a private schema (DB_SCHEMA, default "escalate")."""
    s = get_settings()
    return s.db_schema if s.hosted and url.startswith(("postgres", "postgresql")) else None


def make_engine(url: str) -> Engine:
    schema = pg_schema(url)
    if schema is not None:
        # Small pool (free tier: ~512 MB RAM, a pooler with few connections). No server-side
        # prepared statements, so a transaction-mode pooler can't break queries either.
        pg = create_engine(
            sqlalchemy_url(url),
            pool_size=3,
            max_overflow=2,
            pool_pre_ping=True,
            pool_recycle=300,
            connect_args={"prepare_threshold": None},
        )
        return pg.execution_options(schema_translate_map={None: schema})
    kwargs: dict[str, Any] = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url or url in ("sqlite://", "sqlite:///"):
            from sqlalchemy.pool import StaticPool

            kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        event.listen(engine, "connect", _sqlite_pragmas)
    return engine


def _sqlite_pragmas(dbapi_conn: Any, _record: Any) -> None:
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA secure_delete=ON")  # deleted rows are overwritten, not just unlinked
    cur.close()


def scrub() -> None:
    """After a bulk delete: rebuild the SQLite file (VACUUM) and empty the WAL, so deleted case
    text is not left in free pages or the write-ahead log."""
    engine = get_engine()
    if engine.dialect.name != "sqlite":
        return
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql("VACUUM")
        conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")


def configure(url: str | None = None) -> Engine:
    """(Re)bind the global engine; tests call this with an in-memory URL."""
    global _engine, _factory
    _engine = make_engine(url or get_settings().database_url)
    _factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_engine() -> Engine:
    return _engine or configure()


def session_factory() -> sessionmaker[Session]:
    if _factory is None:
        configure()
    assert _factory is not None
    return _factory


@contextmanager
def session_scope() -> Iterator[Session]:
    """Commit on success, roll back on error."""
    session = session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
