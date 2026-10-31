"""Hosted Postgres (Supabase): keep Escalate's tables away from Supabase's Data API.

The tables live in a private schema (DB_SCHEMA) that the Data API does not expose. As a second
wall, every table in it has row level security on with no policies, and Supabase's API roles
(anon, authenticated) get no rights on the schema at all. Escalate's server connects as the
tables' owner, which RLS does not restrict.
"""

from sqlalchemy import Connection, inspect, text

API_ROLES = ("anon", "authenticated")


def lock_down(conn: Connection, schema: str) -> list[str]:
    """Idempotent. Returns the tables it covered (Postgres only; nothing elsewhere)."""
    if conn.dialect.name != "postgresql":
        return []
    q = conn.dialect.identifier_preparer.quote
    tables = sorted(inspect(conn).get_table_names(schema=schema))
    for table in tables:
        # Identifiers come from the catalog and are quoted by SQLAlchemy's preparer.
        conn.exec_driver_sql(f"ALTER TABLE {q(schema)}.{q(table)} ENABLE ROW LEVEL SECURITY")
    roles = conn.scalars(
        text("SELECT rolname FROM pg_roles WHERE rolname = ANY(:names)"),
        {"names": list(API_ROLES)},
    ).all()
    for role in sorted(roles):
        for what in ("SCHEMA", "ALL TABLES IN SCHEMA", "ALL SEQUENCES IN SCHEMA"):
            conn.exec_driver_sql(f"REVOKE ALL ON {what} {q(schema)} FROM {q(role)}")
        conn.exec_driver_sql(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {q(schema)} REVOKE ALL ON TABLES FROM {q(role)}"
        )
    return tables


def rls_disabled(conn: Connection, schema: str) -> list[str]:
    """Tables in `schema` without row level security (for tests and the startup check)."""
    rows = conn.execute(
        text(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = :schema AND c.relkind = 'r' AND NOT c.relrowsecurity"
        ),
        {"schema": schema},
    )
    return sorted(r[0] for r in rows)
