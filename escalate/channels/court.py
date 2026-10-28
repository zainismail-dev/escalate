"""Consumer court filing: a printable complaint; marked sent when the user uploads filing proof."""

from escalate.channels.base import Attachment, SendResult
from escalate.channels.gate import require_approval
from escalate.db.models import Message


class CourtChannel:
    name = "court"
    note = (
        "Print the complaint with the case file, file it at the court office, then upload the "
        "stamped copy or filing receipt."
    )

    def send(self, msg: Message, attachments: list[Attachment]) -> SendResult:
        require_approval(msg)
        return SendResult(delivered=False, note=self.note)
