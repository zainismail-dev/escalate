"""Channel interface. A channel's send() must call require_approval() before anything else."""

from dataclasses import dataclass, field
from typing import Protocol

from escalate.db.models import Message


@dataclass
class Attachment:
    filename: str
    data: bytes
    mimetype: str = "application/octet-stream"


@dataclass
class SendResult:
    delivered: bool  # False = the user must deliver it (post, court, web form) and confirm
    external_id: str | None = None
    note: str = ""
    extra: dict[str, str] = field(default_factory=dict)


class Channel(Protocol):
    name: str

    def send(self, msg: Message, attachments: list[Attachment]) -> SendResult: ...
