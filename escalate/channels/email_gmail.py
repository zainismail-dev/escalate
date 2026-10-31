"""Optional Gmail API sender (scope gmail.send only). The OAuth token is stored Fernet-encrypted.

Set it up once with: uv run python scripts/gmail_auth.py path/to/client_secret.json
"""

import base64
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet

from escalate.channels.base import Attachment, SendResult
from escalate.channels.email_smtp import EmailConfigError, build_mime
from escalate.channels.gate import refuse_when_hosted, require_approval
from escalate.config import Settings, get_settings
from escalate.db.models import Message

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
TOKEN_PATH = Path("secrets/gmail_token.enc")


def save_token(token_json: str, settings: Settings | None = None, path: Path = TOKEN_PATH) -> None:
    s = settings or get_settings()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(Fernet(s.fernet_key.encode()).encrypt(token_json.encode()))


def load_token(settings: Settings | None = None, path: Path = TOKEN_PATH) -> dict[str, Any]:
    s = settings or get_settings()
    if not path.is_file():
        raise EmailConfigError("Gmail is not connected: run scripts/gmail_auth.py first")
    data: dict[str, Any] = json.loads(Fernet(s.fernet_key.encode()).decrypt(path.read_bytes()))
    return data


def _default_service(settings: Settings) -> Any:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_info(load_token(settings), SCOPES)
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


class GmailApiChannel:
    name = "email"

    def __init__(
        self,
        settings: Settings | None = None,
        service_factory: Callable[[Settings], Any] = _default_service,
        sender: str | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.service_factory = service_factory
        self.sender = sender or self.settings.smtp_user or "me"

    def send(self, msg: Message, attachments: list[Attachment]) -> SendResult:
        require_approval(msg)
        refuse_when_hosted()
        mime = build_mime(msg, self.sender, attachments)
        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
        service = self.service_factory(self.settings)
        sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return SendResult(delivered=True, external_id=str(sent.get("id")))
