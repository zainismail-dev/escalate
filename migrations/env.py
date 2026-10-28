"""Alembic environment: the database URL comes from DATABASE_URL via escalate.config."""

from logging.config import fileConfig

from alembic import context

from escalate.config import get_settings
from escalate.db.models import Base
from escalate.db.session import make_engine

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
    engine = make_engine(_url())
    with engine.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, render_as_batch=True
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
