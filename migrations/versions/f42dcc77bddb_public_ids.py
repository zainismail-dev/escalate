"""public ids (UUIDs) for cases and messages

Revision ID: f42dcc77bddb
Revises: e73f0d0b09bd
Create Date: 2026-10-29 12:00:00

The API exposes only these unguessable ids; integer keys stay internal.
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f42dcc77bddb"
down_revision: str | Sequence[str] | None = "e73f0d0b09bd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("cases", "messages")


def upgrade() -> None:
    bind = op.get_bind()
    for table in TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column("public_id", sa.String(length=36), nullable=True))
        for (row_id,) in bind.execute(sa.text(f"SELECT id FROM {table}")).all():
            bind.execute(
                sa.text(f"UPDATE {table} SET public_id = :p WHERE id = :id"),
                {"p": str(uuid.uuid4()), "id": row_id},
            )
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.alter_column("public_id", existing_type=sa.String(length=36), nullable=False)
            batch_op.create_index(f"ix_{table}_public_id", ["public_id"], unique=True)


def downgrade() -> None:
    for table in TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_index(f"ix_{table}_public_id")
            batch_op.drop_column("public_id")
