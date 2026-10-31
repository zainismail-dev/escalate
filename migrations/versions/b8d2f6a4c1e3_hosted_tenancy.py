"""hosted beta: user_id on every user-owned table; users, user_settings, invites, ai_usage

Revision ID: b8d2f6a4c1e3
Revises: a1c3e5f7b9d2
Create Date: 2026-10-31 12:00:00

Local mode leaves user_id NULL everywhere. Hosted Postgres: the tables are in DB_SCHEMA with row
level security on and no rights for Supabase's API roles (escalate/db/hosted.py).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from escalate.config import get_settings
from escalate.db.hosted import lock_down

revision: str = "b8d2f6a4c1e3"
down_revision: str | Sequence[str] | None = "a1c3e5f7b9d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OWNED = ("cases", "case_facts", "evidence", "messages", "events", "recipient_contacts")


def upgrade() -> None:
    for table in OWNED:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("user_id", sa.String(length=64), nullable=True))
            batch.create_index(f"ix_{table}_user_id", ["user_id"])
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("consented_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "user_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("default_country", sa.String(length=2), nullable=True),
        sa.Column("default_language", sa.String(length=35), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_user_settings_user_id"),
    )
    op.create_index("ix_user_settings_user_id", "user_settings", ["user_id"])
    op.create_table(
        "invites",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("email"),
    )
    op.create_table(
        "ai_usage",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("calls", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "day"),
    )
    settings = get_settings()
    if settings.hosted:
        lock_down(op.get_bind(), settings.db_schema)


def downgrade() -> None:
    op.drop_table("ai_usage")
    op.drop_table("invites")
    op.drop_index("ix_user_settings_user_id", table_name="user_settings")
    op.drop_table("user_settings")
    op.drop_table("users")
    for table in reversed(OWNED):
        with op.batch_alter_table(table) as batch:
            batch.drop_index(f"ix_{table}_user_id")
            batch.drop_column("user_id")
