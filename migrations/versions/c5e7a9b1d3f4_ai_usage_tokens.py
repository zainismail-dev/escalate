"""ai_usage: estimated tokens and failed calls per user per day

Revision ID: c5e7a9b1d3f4
Revises: b8d2f6a4c1e3
Create Date: 2026-11-09 12:00:00

The AI budget counted calls only, so one huge prompt cost the same as a tiny one, and failed
calls were free (escalate/llm/quota.py).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c5e7a9b1d3f4"
down_revision: str | Sequence[str] | None = "b8d2f6a4c1e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = ("tokens", "failures")


def upgrade() -> None:
    with op.batch_alter_table("ai_usage", schema=None) as batch_op:
        for name in COLUMNS:
            batch_op.add_column(sa.Column(name, sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("ai_usage", schema=None) as batch_op:
        for name in reversed(COLUMNS):
            batch_op.drop_column(name)
