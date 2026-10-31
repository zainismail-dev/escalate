"""Hosted sending: the approval gate is unchanged, and the platform never sends email. After
approval the user sends the letter from their own mailbox and confirms "I've sent it"."""

from collections.abc import Iterator

import pytest
from sqlalchemy import select

from escalate.channels import override_channel
from escalate.channels.email_gmail import GmailApiChannel
from escalate.channels.email_smtp import SmtpChannel
from escalate.channels.gate import PlatformSendDisabled
from escalate.config import get_settings
from escalate.db.models import Event, Message, utcnow
from escalate.db.session import session_scope
from tests.factories import LED_TEXT
from tests.fakes.fake_smtp import FakeSMTP
from tests.hosted.conftest import Account, Hosted


@pytest.fixture
def smtp_override(hosted: Hosted) -> Iterator[None]:
    """Even a configured SMTP channel (as local mode would have) must never be used."""
    FakeSMTP.reset()
    s = get_settings().model_copy(update={"smtp_user": "me@example.com", "smtp_app_password": "x"})
    override_channel("email", SmtpChannel(s, smtp_factory=FakeSMTP))
    yield
    override_channel("email", None)


def started(acct: Account) -> tuple[str, dict[str, str]]:
    c = acct.client
    cid = c.post("/cases", json={"description": LED_TEXT, "country": "PK"}).json()["id"]
    c.post(f"/cases/{cid}/evidence", files={"file": ("r.txt", b"BM-48213", "text/plain")})
    run = c.post(f"/cases/{cid}/start").json()
    assert run["waiting_for"] == "approve_draft", run
    return cid, run["pending"]["draft"]


def test_approving_hands_the_letter_to_the_user_and_nothing_is_sent(
    hosted: Hosted, smtp_override: None
) -> None:
    alice = hosted.account("alice@example.com")
    _, draft = started(alice)
    mid = draft["message_id"]
    body = {"confirm": True, "recipient": draft["recipient"]}
    run = alice.client.post(f"/messages/{mid}/approve", json=body).json()
    assert run["waiting_for"] == "confirm_delivery"
    assert run["pending"]["channel"] == "email"
    assert "your own email app" in run["pending"]["note"]
    assert FakeSMTP.all_sent() == []
    with session_scope() as s:
        msg = s.scalar(select(Message).where(Message.public_id == mid))
        assert msg is not None and msg.status == "approved" and msg.sent_at is None

    # the letter is available to copy, open in a mail app, or download
    review = alice.client.get(f"/messages/{mid}/review").json()
    assert review["message"]["recipient"] == draft["recipient"] and review["message"]["body"]

    done = alice.client.post(f"/messages/{mid}/confirm-delivery", json={"evidence_id": None})
    assert done.status_code == 200 and done.json()["waiting_for"] == "waiting_reply"
    assert FakeSMTP.all_sent() == []
    with session_scope() as s:
        sent = s.scalars(select(Event).where(Event.type == "message_sent")).all()
        assert [e.payload["sent_by"] for e in sent] == ["user"]
        assert sent[0].payload["how"] == "user_confirmed"


def test_confirming_without_approval_is_refused(hosted: Hosted) -> None:
    alice = hosted.account("alice@example.com")
    _, draft = started(alice)
    r = alice.client.post(
        f"/messages/{draft['message_id']}/confirm-delivery", json={"evidence_id": None}
    )
    assert r.status_code == 409  # not waiting for delivery: it isn't approved yet


def test_the_email_channels_refuse_to_send_in_hosted_mode(hosted_env: dict[str, str]) -> None:
    msg = Message(id=1, case_id=1, step_id="s", direction="out", channel="email", body="b")
    msg.status, msg.approved_at, msg.recipient = "approved", utcnow(), "x@example.com"
    FakeSMTP.reset()
    with pytest.raises(PlatformSendDisabled):
        SmtpChannel(get_settings(), smtp_factory=FakeSMTP).send(msg, [])
    with pytest.raises(PlatformSendDisabled):
        GmailApiChannel(get_settings(), service_factory=lambda _s: None).send(msg, [])
    assert FakeSMTP.all_sent() == []
