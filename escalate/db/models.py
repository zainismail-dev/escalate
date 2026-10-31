"""SQLAlchemy models (section 5). Countries, regions, languages and currencies are ISO codes."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column, relationship


def utcnow() -> datetime:
    """Naive UTC now (SQLite stores naive datetimes); freezegun-friendly."""
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase): ...


class Owned:
    """A row that belongs to one user. Hosted mode: the Supabase auth user id (`sub`), set on
    every row and filtered on every query (escalate/db/tenancy.py). Local mode: always NULL."""

    @declared_attr
    def user_id(cls) -> Mapped[str | None]:
        return mapped_column(String(64), index=True)


class CaseStatus(StrEnum):
    INTAKE = "intake"
    URGENT = "urgent_checklist"
    DRAFTING = "drafting"
    AWAITING_APPROVAL = "awaiting_approval"
    WAITING_REPLY = "waiting_reply"
    CONFIRM_RESOLUTION = "confirm_resolution"  # the reply looks like a resolution: user confirms
    PICK_NEXT = "pick_next"
    RESOLVED = "resolved"
    CLOSED_UNRESOLVED = "closed_unresolved"
    WITHDRAWN = "withdrawn"


def new_public_id() -> str:
    """Unguessable id for the API (internal integer ids are never exposed)."""
    return str(uuid.uuid4())


class Case(Owned, Base):
    __tablename__ = "cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(
        String(36), unique=True, index=True, default=new_public_id
    )
    description: Mapped[str] = mapped_column(Text, default="")  # the user's own words
    title: Mapped[str | None] = mapped_column(String(160))  # from facts at intake, or the user's
    case_type: Mapped[str | None] = mapped_column(String(40))  # refund_refused | ... | scam
    country: Mapped[str | None] = mapped_column(String(2))  # ISO 3166-1; set by user or classify
    region: Mapped[str | None] = mapped_column(String(10))  # ISO 3166-2, e.g. US-CA, PK-SD
    language: Mapped[str] = mapped_column(String(5), default="en")  # ISO 639-1 for drafts
    company: Mapped[str | None] = mapped_column(String(200))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(3))  # ISO 4217
    status: Mapped[str] = mapped_column(String(30), default=CaseStatus.INTAKE)
    playbook_id: Mapped[str | None] = mapped_column(String(120))
    playbook_version: Mapped[str | None] = mapped_column(String(20))
    current_step: Mapped[str | None] = mapped_column(String(80))
    next_action_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    facts: Mapped[list["CaseFact"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", passive_deletes=True
    )
    evidence: Mapped[list["Evidence"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", passive_deletes=True
    )
    messages: Mapped[list["Message"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", passive_deletes=True
    )
    events: Mapped[list["Event"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Event.id",
    )

    def fact_dict(self) -> dict[str, str]:
        return {f.key: f.value for f in self.facts}


class CaseFact(Owned, Base):
    __tablename__ = "case_facts"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(80))  # e.g. order_id, return_shipped_on
    value: Mapped[str] = mapped_column(Text)
    source_evidence_id: Mapped[int | None] = mapped_column(
        ForeignKey("evidence.id", ondelete="SET NULL")
    )
    confidence: Mapped[float] = mapped_column(default=1.0)
    case: Mapped[Case] = relationship(back_populates="facts")


class Evidence(Owned, Base):
    __tablename__ = "evidence"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # image | pdf | email | text | other
    filename: Mapped[str] = mapped_column(String(300), default="")
    file_path: Mapped[str] = mapped_column(String(500))  # encrypted file
    sha256: Mapped[str] = mapped_column(String(64))
    extracted_text: Mapped[str | None] = mapped_column(Text)
    ocr_confidence: Mapped[float | None]
    needs_review: Mapped[bool] = mapped_column(default=False)
    uploaded_at: Mapped[datetime] = mapped_column(default=utcnow)
    case: Mapped[Case] = relationship(back_populates="evidence")


class Message(Owned, Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(
        String(36), unique=True, index=True, default=new_public_id
    )
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    step_id: Mapped[str] = mapped_column(String(80))
    direction: Mapped[str] = mapped_column(String(3))  # out | in
    channel: Mapped[str] = mapped_column(String(20))  # email | post | court | web_form | info
    recipient: Mapped[str | None] = mapped_column(String(300))
    subject: Mapped[str | None] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    original_body: Mapped[str | None] = mapped_column(Text)  # as drafted and fact-checked
    # draft | approved | sent | received | rejected | superseded
    status: Mapped[str] = mapped_column(String(20), default="draft")
    approved_at: Mapped[datetime | None]
    sent_at: Mapped[datetime | None]
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(String(200))  # e.g. Gmail message id
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    case: Mapped[Case] = relationship(back_populates="messages")


class Event(Owned, Base):
    __tablename__ = "events"  # append-only audit log
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    case: Mapped[Case] = relationship(back_populates="events")


class RecipientContact(Owned, Base):
    """One approved letter to a recipient, kept only as hashes (anti-harassment counting).
    No foreign key and no PII: it survives case deletion, so deleting cases can't reset the
    limit, and it can't be turned back into an address (HMAC keyed by FERNET_KEY)."""

    __tablename__ = "recipient_contacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    recipient_hash: Mapped[str] = mapped_column(String(64), index=True)
    case_hash: Mapped[str] = mapped_column(String(64))
    contacted_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


class User(Base):
    """Hosted mode: a signed-in Supabase user (created on first request)."""

    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # Supabase auth user id
    email: Mapped[str] = mapped_column(String(320))
    consented_at: Mapped[datetime | None]  # the first-run consent (AI processing, beta, ...)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class UserSettings(Owned, Base):
    """Hosted mode: what a user may change (the AI provider and email are the server's)."""

    __tablename__ = "user_settings"
    __table_args__ = (UniqueConstraint("user_id", name="uq_user_settings_user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    default_country: Mapped[str | None] = mapped_column(String(2))
    default_language: Mapped[str | None] = mapped_column(String(35))


class Invite(Base):
    """Hosted mode: who may use the beta (`make invite EMAIL=...`). Everyone else: waitlist."""

    __tablename__ = "invites"
    email: Mapped[str] = mapped_column(String(320), primary_key=True)  # lower-case
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


GLOBAL_USAGE = "*"  # the ai_usage row counting every user's calls


class AiUsage(Base):
    """Hosted mode: AI calls per user per UTC day, and all users together (user_id "*")."""

    __tablename__ = "ai_usage"
    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    day: Mapped[date] = mapped_column(primary_key=True)
    calls: Mapped[int] = mapped_column(default=0)
