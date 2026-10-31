"""Alembic environment: the database URL comes from DATABASE_URL via escalate.config."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection
from sqlalchemy.schema import CreateSchema

from escalate.config import get_settings
from escalate.db.models import Base
from escalate.db.session import make_engine, pg_schema

config = context.config
# The `alembic` CLI configures logging from alembic.ini. Inside the API (init_db) it must not:
# fileConfig() would replace the app's handlers and, by default, disable every existing logger,
# which silences uvicorn ("Application startup complete", access logs, tracebacks).
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _url() -> str:
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = _url()
    schema = pg_schema(url)  # hosted Postgres: every table, and alembic_version, in DB_SCHEMA
    engine = make_engine(url)
    with engine.connect() as connection:
        if schema is not None:
            _create_schema(connection, schema)
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            version_table_schema=schema,
        )
        with context.begin_transaction():
            context.run_migrations()


def _create_schema(connection: Connection, schema: str) -> None:
    """Create DB_SCHEMA and make it this connection's search_path: Alembic's ALTER statements
    name tables without a schema (schema_translate_map only covers CREATE)."""
    connection.execute(CreateSchema(schema, if_not_exists=True))
    quoted = connection.dialect.identifier_preparer.quote(schema)
    connection.exec_driver_sql(f"SET search_path TO {quoted}")
    connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
