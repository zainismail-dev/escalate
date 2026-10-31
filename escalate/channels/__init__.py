"""Channel registry and the one place that records a send.

`send_message` is idempotent: a message that already has `sent_at` is returned unchanged.
Channels the user delivers themselves (post, court, web form) are marked sent only when the user
confirms delivery, with proof uploaded as evidence where the playbook requires it.
"""

from collections.abc import Callable

from sqlalchemy.orm import Session

from escalate.channels.base import Attachment, Channel, SendResult
from escalate.channels.court import CourtChannel
from escalate.channels.gate import NotApproved, require_approval
from escalate.channels.post import PostChannel, UserDeliveredChannel
from escalate.config import get_settings
from escalate.db.events import log_event
from escalate.db.models import Evidence, Message, utcnow


class DemoEmailChannel:
    """DEMO_MODE: approval is still required, but nothing leaves the machine."""

    name = "email"

    def send(self, msg: Message, attachments: list[Attachment]) -> SendResult:
        require_approval(msg)
        return SendResult(delivered=True, external_id=f"demo-{msg.id}", note="demo: not sent")


HOSTED_EMAIL_NOTE = (
    "Open the letter in your own email app (or copy it), send it yourself, then confirm here."
)


def _email() -> Channel:
    if get_settings().hosted:  # the user sends it from their own mailbox, then confirms
        return UserDeliveredChannel("email", HOSTED_EMAIL_NOTE)
    if get_settings().demo_mode:
        return DemoEmailChannel()
    if get_settings().email_mode == "gmail_api":
        from escalate.channels.email_gmail import GmailApiChannel

        return GmailApiChannel()
    from escalate.channels.email_smtp import SmtpChannel

    return SmtpChannel()


_REGISTRY: dict[str, Callable[[], Channel]] = {
    "email": _email,
    "post": PostChannel,
    "court": CourtChannel,
    "web_form": lambda: UserDeliveredChannel(
        "web_form", "Paste this text into the company's or authority's online form, then confirm."
    ),
    "info": lambda: UserDeliveredChannel("info", "This is a guide for you; nothing is sent."),
}
_overrides: dict[str, Channel] = {}


def get_channel(name: str) -> Channel:
    s = get_settings()
    if name in _overrides and not (name == "email" and (s.demo_mode or s.hosted)):
        return _overrides[name]
    try:
        return _REGISTRY[name]()
    except KeyError:
        raise ValueError(f"unknown channel {name!r}") from None


def override_channel(name: str, channel: Channel | None) -> None:
    """Tests (and DEMO_MODE) swap a channel implementation."""
    if channel is None:
        _overrides.pop(name, None)
    else:
        _overrides[name] = channel


def _mark_sent(session: Session, msg: Message, result: SendResult, how: str) -> None:
    msg.status = "sent"
    msg.sent_at = utcnow()
    msg.external_id = result.external_id
    session.flush()
    payload = {"message_id": msg.id, "step": msg.step_id, "channel": msg.channel, "how": how}
    if get_settings().hosted:
        payload["sent_by"] = "user" if how in ("user_confirmed", "info") else "platform"
    log_event(session, msg.case_id, "message_sent", payload)


def send_message(
    session: Session, message_id: int, attachments: list[Attachment] | None = None
) -> SendResult:
    msg = session.get(Message, message_id)
    if msg is None:
        raise ValueError(f"message {message_id} not found")
    if msg.sent_at is not None:
        return SendResult(delivered=True, external_id=msg.external_id, note="already sent")
    require_approval(msg)
    channel = get_channel(msg.channel)
    result = channel.send(msg, attachments or [])
    if result.delivered:
        _mark_sent(session, msg, result, how=channel.name)
    elif msg.channel == "info":
        _mark_sent(session, msg, result, how="info")
        result.delivered = True
    else:
        log_event(
            session,
            msg.case_id,
            "awaiting_user_delivery",
            {"message_id": msg.id, "channel": msg.channel, "note": result.note},
        )
    return result


class ProofRequired(Exception):
    pass


def confirm_delivery(
    session: Session, message_id: int, proof: Evidence | None = None, proof_needed: bool = False
) -> Message:
    """The user says they posted/filed/submitted it. Post and court need uploaded proof."""
    msg = session.get(Message, message_id)
    if msg is None:
        raise ValueError(f"message {message_id} not found")
    if msg.sent_at is not None:
        return msg  # idempotent
    require_approval(msg)
    if (proof_needed or msg.channel in ("post", "court")) and proof is None:
        raise ProofRequired(f"upload the delivery or filing receipt for message {msg.id}")
    if proof is not None and proof.case_id != msg.case_id:
        raise ProofRequired("the proof belongs to a different case")
    result = SendResult(delivered=True, external_id=f"evidence:{proof.id}" if proof else None)
    _mark_sent(session, msg, result, how="user_confirmed")
    return msg


__all__ = [
    "Attachment",
    "Channel",
    "NotApproved",
    "ProofRequired",
    "SendResult",
    "confirm_delivery",
    "get_channel",
    "override_channel",
    "send_message",
]
