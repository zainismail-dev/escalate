"""Request and response models for the REST API."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Orm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CaseCreate(BaseModel):
    description: str = Field(min_length=10, max_length=20_000)
    country: str | None = Field(default=None, description="ISO 3166-1 alpha-2")
    region: str | None = Field(default=None, description="ISO 3166-2, e.g. PK-SD")
    language: str = Field(default="en", description="ISO 639-1 language for drafts")
    company: str | None = None

    @field_validator("country", "region", mode="before")
    @classmethod
    def _upper(cls, v: object) -> object:
        return (v.strip().upper() or None) if isinstance(v, str) else v

    @field_validator("country")
    @classmethod
    def _iso_country(cls, v: str | None) -> str | None:
        if v is not None and (len(v) != 2 or not v.isalpha()):
            raise ValueError("country must be an ISO 3166-1 alpha-2 code, e.g. PK")
        return v

    @field_validator("language")
    @classmethod
    def _iso_lang(cls, v: str) -> str:
        v = v.strip().lower()
        if len(v) != 2 or not v.isalpha():
            raise ValueError("language must be an ISO 639-1 code, e.g. en")
        return v


class FactOut(Orm):
    key: str
    value: str
    confidence: float
    source_evidence_id: int | None


class EvidenceOut(Orm):
    id: int
    kind: str
    filename: str
    sha256: str
    needs_review: bool
    ocr_confidence: float | None
    uploaded_at: datetime
    extracted_text: str | None = None


class MessageOut(Orm):
    id: int
    step_id: str
    direction: str
    channel: str
    recipient: str | None
    subject: str | None
    body: str
    status: str
    approved_at: datetime | None
    sent_at: datetime | None
    rejection_reason: str | None
    created_at: datetime


class EventOut(Orm):
    id: int
    type: str
    payload: dict[str, Any]
    created_at: datetime


class DeadlineOut(BaseModel):
    id: str
    rule: str
    due: date | None
    days_left: int | None
    warn: bool
    late: bool


class CaseOut(Orm):
    id: int
    case_type: str | None
    country: str | None
    region: str | None
    language: str
    company: str | None
    amount: Decimal | None
    currency: str | None
    status: str
    playbook_id: str | None
    current_step: str | None
    next_action_at: datetime | None
    created_at: datetime


class CaseDetail(CaseOut):
    description: str
    playbook_version: str | None
    generic_playbook: bool = False
    facts: list[FactOut]
    evidence: list[EvidenceOut]
    messages: list[MessageOut]
    pending: dict[str, Any] | None = None
    pending_draft: MessageOut | None = None
    deadlines: list[DeadlineOut] = Field(default_factory=list)
    step_name: str | None = None


class RunOut(BaseModel):
    case_id: int
    waiting_for: str | None
    pending: dict[str, Any] | None
    warnings: list[str] = Field(default_factory=list)


class AnswersIn(BaseModel):
    answers: dict[str, str]


class MessageEdit(BaseModel):
    body: str = Field(min_length=1)
    subject: str | None = None


class ApproveIn(BaseModel):
    body: str | None = None
    subject: str | None = None


class RejectIn(BaseModel):
    reason: str = ""


class ReplyIn(BaseModel):
    text: str = Field(min_length=1, max_length=50_000)


class ReplyOut(RunOut):
    verdict: str | None = None
    reason: str | None = None


class DeliveryIn(BaseModel):
    evidence_id: int | None = None


class WithdrawIn(BaseModel):
    reason: str = ""


class EditOut(BaseModel):
    message: MessageOut
    warnings: list[str]


class HealthOut(BaseModel):
    ok: bool
    version: str
    is_cloud: bool
    llm_base_url: str
    demo_mode: bool
    email_mode: str
