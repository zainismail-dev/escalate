"""evidence.size_bytes: the per-user storage cap in hosted mode

Revision ID: d6f8b0c2e4a5
Revises: c5e7a9b1d3f4
Create Date: 2026-11-09 13:00:00

Files uploaded before this revision count as 0 bytes.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d6f8b0c2e4a5"
down_revision: str | Sequence[str] | None = "c5e7a9b1d3f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("evidence", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("evidence", schema=None) as batch_op:
        batch_op.drop_column("size_bytes")
