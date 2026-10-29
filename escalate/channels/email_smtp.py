"""Send email from the user's own address with an app password: any provider's SMTP server.

Port 465 uses SSL; any other port (usually 587) uses STARTTLS. The default is Gmail.
"""

import re
import smtplib
import ssl
from collections.abc import Callable
from email.message import EmailMessage
from email.utils import make_msgid

from escalate.channels.base import Attachment, SendResult
from escalate.channels.gate import require_approval
from escalate.config import Settings, get_settings
from escalate.db.models import Message

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SmtpFactory = Callable[[str, int], smtplib.SMTP]


class EmailConfigError(RuntimeError):
    pass


def build_mime(msg: Message, sender: str, attachments: list[Attachment]) -> EmailMessage:
    if not msg.recipient or not EMAIL_RE.match(msg.recipient.strip()):
        raise EmailConfigError(f"message {msg.id}: recipient {msg.recipient!r} is not an email")
    mime = EmailMessage()
    mime["From"] = sender
    mime["To"] = msg.recipient.strip()
    mime["Subject"] = msg.subject or ""
    mime["Message-ID"] = make_msgid(domain=sender.split("@")[-1])
    mime.set_content(msg.body)
    for a in attachments:
        maintype, _, subtype = a.mimetype.partition("/")
        mime.add_attachment(a.data, maintype=maintype, subtype=subtype, filename=a.filename)
    return mime


def tls_context() -> ssl.SSLContext:
    """Verify the server's certificate and hostname. (smtplib's own default does neither, so a
    network attacker could otherwise read the app password.)"""
    return ssl.create_default_context()


def _ssl_factory(host: str, port: int) -> smtplib.SMTP:
    if port == 465:
        return smtplib.SMTP_SSL(host, port, timeout=30, context=tls_context())
    smtp = smtplib.SMTP(host, port, timeout=30)
    smtp.starttls(context=tls_context())
    return smtp


class SmtpChannel:
    name = "email"

    def __init__(
        self,
        settings: Settings | None = None,
        smtp_factory: SmtpFactory = _ssl_factory,
        host: str | None = None,
        port: int | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.smtp_factory = smtp_factory
        self.host = host or self.settings.smtp_host
        self.port = port or self.settings.smtp_port

    def send(self, msg: Message, attachments: list[Attachment]) -> SendResult:
        require_approval(msg)
        user, password = self.settings.smtp_user, self.settings.smtp_app_password
        if not user or not password:
            raise EmailConfigError("set SMTP_USER and SMTP_APP_PASSWORD in .env to send email")
        mime = build_mime(msg, user, attachments)
        with self.smtp_factory(self.host, self.port) as smtp:
            smtp.login(user, password)
            smtp.send_message(mime)
        return SendResult(delivered=True, external_id=str(mime["Message-ID"]))
