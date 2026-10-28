"""case title (with backfill from facts)

Revision ID: e73f0d0b09bd
Revises: e4a9cc27e4b4
Create Date: 2026-10-29 09:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e73f0d0b09bd"
down_revision: str | Sequence[str] | None = "e4a9cc27e4b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _short(text: str, limit: int = 60) -> str:
    text = " ".join(text.split()).rstrip(".")
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def _title(case_type: str | None, facts: dict[str, str], company: str | None) -> str:
    """Frozen copy of escalate.agent.titles.auto_title as of this migration (facts only)."""

    def f(*keys: str) -> str | None:
        for k in keys:
            if (facts.get(k) or "").strip():
                return _short(facts[k])
        return None

    def cap(t: str) -> str:
        return t[:1].upper() + t[1:]

    if case_type == "refund_refused":
        if product := f("product"):
            return cap(f"{product} — refund refused")
        seller = f("seller_name") or company
        return f"Refund refused by {seller}" if seller else "Refund refused"
    if case_type == "subscription_cancel":
        what = f("plan_name", "company_name") or company
        if what:
            return cap(f"{what} still charging after cancelling")
        return "Subscription still charging after cancelling"
    if case_type == "scam":
        if method := f("payment_method"):
            return f"Scam payment by {method}"
        if scammer := f("scammer_name"):
            return f"Scam payment to {scammer}"
        return "Suspected scam payment"
    return f"Complaint about {company}" if company else "Consumer complaint"


def upgrade() -> None:
    with op.batch_alter_table("cases", schema=None) as batch_op:
        batch_op.add_column(sa.Column("title", sa.String(length=160), nullable=True))

    bind = op.get_bind()
    cases = bind.execute(sa.text("SELECT id, case_type, company FROM cases")).all()
    for case_id, case_type, company in cases:
        rows = bind.execute(
            sa.text("SELECT key, value FROM case_facts WHERE case_id = :id"), {"id": case_id}
        ).all()
        if not rows and not case_type:
            continue  # nothing known yet: the agent sets the title at intake
        facts = {k: v for k, v in rows}
        bind.execute(
            sa.text("UPDATE cases SET title = :t WHERE id = :id AND title IS NULL"),
            {"t": _title(case_type, facts, company)[:120], "id": case_id},
        )


def downgrade() -> None:
    with op.batch_alter_table("cases", schema=None) as batch_op:
        batch_op.drop_column("title")
