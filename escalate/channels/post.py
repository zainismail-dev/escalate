"""Registered post / hand delivery: we make a printable PDF; the user posts it and uploads proof."""

from escalate.channels.base import Attachment, SendResult
from escalate.channels.gate import require_approval
from escalate.db.models import Message


class PostChannel:
    name = "post"
    note = "Print the letter, send it by registered post or courier, then upload the receipt."

    def send(self, msg: Message, attachments: list[Attachment]) -> SendResult:
        require_approval(msg)
        return SendResult(delivered=False, note=self.note)


class UserDeliveredChannel:
    """web_form / info: the user pastes the text into a form (or reads the guide) and confirms."""

    def __init__(self, name: str, note: str) -> None:
        self.name = name
        self.note = note

    def send(self, msg: Message, attachments: list[Attachment]) -> SendResult:
        require_approval(msg)
        return SendResult(delivered=False, note=self.note)
