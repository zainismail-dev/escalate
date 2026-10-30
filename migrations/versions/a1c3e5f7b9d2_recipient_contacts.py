"""recipient_contacts: hashed record of approved recipients (anti-harassment limit)

Revision ID: a1c3e5f7b9d2
Revises: f42dcc77bddb
Create Date: 2026-10-30 10:00:00

Only HMAC hashes are stored; rows outlive case deletion on purpose. Earlier approvals are still
counted from the messages table while their cases exist, so no backfill is needed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1c3e5f7b9d2"
down_revision: str | Sequence[str] | None = "f42dcc77bddb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recipient_contacts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("recipient_hash", sa.String(length=64), nullable=False),
        sa.Column("case_hash", sa.String(length=64), nullable=False),
        sa.Column("contacted_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recipient_contacts_recipient_hash", "recipient_contacts", ["recipient_hash"])
    op.create_index("ix_recipient_contacts_contacted_at", "recipient_contacts", ["contacted_at"])


def downgrade() -> None:
    op.drop_index("ix_recipient_contacts_contacted_at", table_name="recipient_contacts")
    op.drop_index("ix_recipient_contacts_recipient_hash", table_name="recipient_contacts")
    op.drop_table("recipient_contacts")
