"""The approval gate. Every channel's send() calls require_approval() first (CLAUDE.md rule 1)."""

from escalate.config import get_settings
from escalate.db.models import Message


class NotApproved(Exception): ...


class PlatformSendDisabled(NotApproved):
    """Hosted mode: Escalate never sends email itself; the user sends it from their mailbox."""


def refuse_when_hosted() -> None:
    if get_settings().hosted:
        raise PlatformSendDisabled("the hosted beta never sends email: send it yourself")


def require_approval(msg: Message) -> None:
    if msg.status != "approved" or msg.approved_at is None:
        raise NotApproved(f"message {msg.id} not approved")
    if msg.sent_at is not None:
        raise NotApproved(f"message {msg.id} already sent")  # idempotency
