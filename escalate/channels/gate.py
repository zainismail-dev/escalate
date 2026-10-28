"""The approval gate. Every channel's send() calls require_approval() first (CLAUDE.md rule 1)."""

from escalate.db.models import Message


class NotApproved(Exception): ...


def require_approval(msg: Message) -> None:
    if msg.status != "approved" or msg.approved_at is None:
        raise NotApproved(f"message {msg.id} not approved")
    if msg.sent_at is not None:
        raise NotApproved(f"message {msg.id} already sent")  # idempotency
