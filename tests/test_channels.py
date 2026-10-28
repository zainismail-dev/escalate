import base64
import email
from collections.abc import Iterator
from email import policy
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session

from escalate.agent.approval import approve_message
from escalate.agent.draft import draft_step
from escalate.channels import (
    Attachment,
    NotApproved,
    ProofRequired,
    confirm_delivery,
    get_channel,
    override_channel,
    send_message,
)
from escalate.channels.court import CourtChannel
from escalate.channels.email_gmail import GmailApiChannel, load_token, save_token
from escalate.channels.email_smtp import EmailConfigError, SmtpChannel
from escalate.channels.post import PostChannel
from escalate.config import Settings
from escalate.db.models import CaseFact, Evidence, Message
from escalate.export.pdf import letter_pdf, pdf_available
from escalate.playbooks.loader import get_playbook
from tests.factories import led_case
from tests.fakes.fake_smtp import FakeSMTP


@pytest.fixture
def smtp(settings: Settings) -> Iterator[SmtpChannel]:
    FakeSMTP.reset()
    s = settings.model_copy(update={"smtp_user": "me@example.com", "smtp_app_password": "app-pw"})
    ch = SmtpChannel(s, smtp_factory=FakeSMTP)
    override_channel("email", ch)
    yield ch
    override_channel("email", None)


def _msg(db: Session, step: str = "s1_written_demand", approve: bool = True) -> Message:
    case = led_case(db)
    pb = get_playbook("intl-generic-refund-refused")
    msg = draft_step(db, case, pb, pb.step(step), use_llm=False)
    return approve_message(db, msg.id) if approve else msg


def _pk_notice(db: Session, approve: bool = True) -> Message:
    case = led_case(db)
    db.add(CaseFact(case_id=case.id, key="seller_address", value="Shop 4, Saddar, Karachi"))
    db.flush()
    db.refresh(case)
    pb = get_playbook("pk-ecommerce-refund-refused")
    msg = draft_step(db, case, pb, pb.step("s3_legal_notice"), use_llm=False)
    return approve_message(db, msg.id) if approve else msg


# --- email --------------------------------------------------------------------------


def test_smtp_sends_approved_email_with_attachment(db: Session, smtp: SmtpChannel) -> None:
    msg = _msg(db)
    result = send_message(db, msg.id, [Attachment("receipt.txt", b"hello", "text/plain")])
    assert result.delivered
    server = FakeSMTP.instances[0]
    assert (server.host, server.port) == ("smtp.gmail.com", 465)
    assert server.logins == [("me@example.com", "app-pw")]
    sent = server.sent[0]
    assert sent["To"] == "support@brightmart.example"
    assert sent["Subject"] == "Refund request for order BM-48213"
    assert [a.get_filename() for a in sent.iter_attachments()] == ["receipt.txt"]
    assert msg.status == "sent" and msg.sent_at is not None
    assert msg.case.events[-1].type == "message_sent"


def test_send_is_idempotent(db: Session, smtp: SmtpChannel) -> None:
    msg = _msg(db)
    send_message(db, msg.id)
    again = send_message(db, msg.id)
    assert again.note == "already sent"
    assert len(FakeSMTP.all_sent()) == 1
    assert [e.type for e in msg.case.events].count("message_sent") == 1


def test_unapproved_draft_is_never_sent(db: Session, smtp: SmtpChannel) -> None:
    msg = _msg(db, approve=False)
    with pytest.raises(NotApproved):
        send_message(db, msg.id)
    assert FakeSMTP.all_sent() == []
    assert msg.sent_at is None


@pytest.mark.parametrize("make", ["smtp", "gmail", "post", "court", "web_form", "info"])
def test_every_channel_refuses_unapproved(db: Session, settings: Settings, make: str) -> None:
    msg = _msg(db, approve=False)
    channels: dict[str, Any] = {
        "smtp": lambda: SmtpChannel(settings, smtp_factory=FakeSMTP),
        "gmail": lambda: GmailApiChannel(settings, service_factory=lambda s: None),
        "post": PostChannel,
        "court": CourtChannel,
        "web_form": lambda: get_channel("web_form"),
        "info": lambda: get_channel("info"),
    }
    with pytest.raises(NotApproved):
        channels[make]().send(msg, [])


def test_smtp_needs_credentials(db: Session, settings: Settings) -> None:
    msg = _msg(db)
    with pytest.raises(EmailConfigError, match="SMTP_USER"):
        SmtpChannel(settings, smtp_factory=FakeSMTP).send(msg, [])


def test_smtp_rejects_non_email_recipient(db: Session, smtp: SmtpChannel) -> None:
    msg = _msg(db)
    msg.recipient = "WhatsApp 0300-0000000"
    with pytest.raises(EmailConfigError, match="not an email"):
        send_message(db, msg.id)
    assert msg.sent_at is None


class _FakeGmail:
    def __init__(self) -> None:
        self.bodies: list[dict[str, str]] = []

    def users(self) -> "_FakeGmail":
        return self

    def messages(self) -> "_FakeGmail":
        return self

    def send(self, userId: str, body: dict[str, str]) -> "_FakeGmail":
        assert userId == "me"
        self.bodies.append(body)
        return self

    def execute(self) -> dict[str, str]:
        return {"id": "gmail-123"}


def test_gmail_api_sends_raw_mime(db: Session, settings: Settings) -> None:
    fake = _FakeGmail()
    ch = GmailApiChannel(settings, service_factory=lambda s: fake, sender="me@example.com")
    override_channel("email", ch)
    try:
        msg = _msg(db)
        send_message(db, msg.id)
    finally:
        override_channel("email", None)
    raw = base64.urlsafe_b64decode(fake.bodies[0]["raw"])
    parsed = email.message_from_bytes(raw, policy=policy.default)
    assert parsed["To"] == "support@brightmart.example"
    assert msg.external_id == "gmail-123"


def test_gmail_token_is_encrypted(settings: Settings, tmp_path: Path) -> None:
    path = tmp_path / "tok.enc"
    save_token('{"refresh_token": "secret-refresh"}', settings, path)
    assert b"secret-refresh" not in path.read_bytes()
    assert load_token(settings, path)["refresh_token"] == "secret-refresh"


# --- post / court / web form ---------------------------------------------------------


def test_post_waits_for_proof(db: Session) -> None:
    msg = _pk_notice(db)
    assert msg.channel == "post"
    result = send_message(db, msg.id)
    assert not result.delivered
    assert msg.sent_at is None
    assert msg.case.events[-1].type == "awaiting_user_delivery"
    with pytest.raises(ProofRequired):
        confirm_delivery(db, msg.id)

    proof = Evidence(case_id=msg.case_id, kind="image", file_path="r.bin", sha256="1" * 64)
    db.add(proof)
    db.flush()
    confirm_delivery(db, msg.id, proof)
    assert msg.status == "sent" and msg.sent_at is not None
    assert msg.external_id == f"evidence:{proof.id}"
    assert confirm_delivery(db, msg.id, proof) is msg  # idempotent


def test_proof_must_belong_to_same_case(db: Session) -> None:
    msg = _pk_notice(db)
    other = led_case(db)
    proof = Evidence(case_id=other.id, kind="image", file_path="r.bin", sha256="1" * 64)
    db.add(proof)
    db.flush()
    with pytest.raises(ProofRequired, match="different case"):
        confirm_delivery(db, msg.id, proof)


def test_confirm_delivery_needs_approval(db: Session) -> None:
    msg = _pk_notice(db, approve=False)
    with pytest.raises(NotApproved):
        confirm_delivery(db, msg.id)


def test_info_channel_is_marked_sent(db: Session) -> None:
    msg = _msg(db, step="s4_small_claims")
    assert send_message(db, msg.id).delivered
    assert msg.status == "sent"


def test_unknown_channel() -> None:
    with pytest.raises(ValueError):
        get_channel("pigeon")


@pytest.mark.skipif(not pdf_available(), reason="WeasyPrint system libraries not installed")
def test_printable_letter_pdf() -> None:
    pdf = letter_pdf("Legal notice", "Dear seller,\n\nPay PKR 45,000.00.\n\n---\n\nAli")
    assert pdf.startswith(b"%PDF")
