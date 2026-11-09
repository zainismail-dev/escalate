"""public ids (UUIDs) for evidence and events

Revision ID: e8b0d2f4a6c7
Revises: d6f8b0c2e4a5
Create Date: 2026-11-09 14:00:00

Like cases and messages (f42dcc77bddb): the API shows these, never the integer keys.
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e8b0d2f4a6c7"
down_revision: str | Sequence[str] | None = "d6f8b0c2e4a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("evidence", "events")


def upgrade() -> None:
    bind = op.get_bind()
    for table in TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column("public_id", sa.String(length=36), nullable=True))
        # `table` comes from the TABLES constant above; values are bound parameters.
        select_ids = sa.text(f"SELECT id FROM {table}")  # nosemgrep: avoid-sqlalchemy-text
        for (row_id,) in bind.execute(select_ids).all():
            bind.execute(
                sa.text(f"UPDATE {table} SET public_id = :p WHERE id = :id"),  # nosemgrep: avoid-sqlalchemy-text
                {"p": str(uuid.uuid4()), "id": row_id},
            )
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.alter_column("public_id", existing_type=sa.String(length=36), nullable=False)
            batch_op.create_index(f"ix_{table}_public_id", ["public_id"], unique=True)


def downgrade() -> None:
    for table in reversed(TABLES):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_index(f"ix_{table}_public_id")
            batch_op.drop_column("public_id")
