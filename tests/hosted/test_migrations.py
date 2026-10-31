"""Migrations match the models on SQLite, and on Postgres they run up and down inside the
private schema with row level security on every table."""

from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from escalate.db.hosted import lock_down, rls_disabled
from escalate.db.models import Base
from escalate.db.session import make_engine
from tests.hosted.conftest import PG_URL
from tests.hosted.migrate import downgrade, upgrade

needs_pg = pytest.mark.skipif(not PG_URL, reason="TEST_POSTGRES_URL not set (CI hosted job)")


def test_sqlite_migrations_match_the_models(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    upgrade(url)
    engine = create_engine(url)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []
    downgrade(url)
    assert set(inspect(create_engine(url)).get_table_names()) <= {"alembic_version"}


@needs_pg
def test_postgres_up_down_up_in_the_private_schema(hosted_db: object) -> None:
    # hosted_db already ran `upgrade head` into a fresh schema
    engine = make_engine(PG_URL)
    with engine.connect() as conn:
        insp = inspect(conn)
        assert "cases" not in insp.get_table_names(schema="public")
        tables = set(insp.get_table_names(schema="escalate"))
        assert {"cases", "messages", "invites", "ai_usage", "alembic_version"} <= tables
        assert rls_disabled(conn, "escalate") == []
        conn.exec_driver_sql("SET search_path TO escalate")
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        assert diff == []
    downgrade(PG_URL)
    upgrade(PG_URL)
    with engine.begin() as conn:
        assert lock_down(conn, "escalate")  # idempotent
        assert rls_disabled(conn, "escalate") == []


@needs_pg
def test_supabase_api_roles_get_no_access(hosted_db: object) -> None:
    engine = make_engine(PG_URL)
    with engine.begin() as conn:
        for role in ("anon", "authenticated"):
            conn.exec_driver_sql(
                "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '"
                + role
                + "') THEN CREATE ROLE "
                + role
                + "; END IF; END $$"
            )
        lock_down(conn, "escalate")
        for role in ("anon", "authenticated"):
            usage = conn.exec_driver_sql(
                f"SELECT has_schema_privilege('{role}', 'escalate', 'USAGE')"
            ).scalar()
            assert usage is False
