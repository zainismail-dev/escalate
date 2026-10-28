"""Request and response models for the REST API."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from escalate.i18n.countries import letter_language


class Orm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CaseCreate(BaseModel):
    description: str = Field(min_length=10, max_length=20_000)
    country: str | None = Field(default=None, description="ISO 3166-1 alpha-2")
    region: str | None = Field(default=None, description="ISO 3166-2, e.g. PK-SD")
    language: str | None = Field(
        default=None,
        description="BCP-47 letter language; must be in ENABLED_LETTER_LANGUAGES (v0.1: en)",
    )
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
    def _bcp47(cls, v: str | None) -> str | None:
        return letter_language(v) if v else None


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


class LadderStepOut(BaseModel):
    id: str
    name: str
    channel: str
    recipient_role: str | None
    wait_days: int | None
    state: Literal["done", "current", "future", "skipped"]


class ReasonOut(BaseModel):
    code: str
    params: dict[str, Any] = Field(default_factory=dict)


class SourceOut(BaseModel):
    title: str
    url: str | None = None


class CaseSummary(CaseOut):
    """A list row: enough for the My cases cards and the mini ladder."""

    waiting_for: str | None = None
    generic_playbook: bool = False
    step_name: str | None = None
    ladder: list[LadderStepOut] = Field(default_factory=list)
    deadline_warning: bool = False


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
    waiting_for: str | None = None
    ladder: list[LadderStepOut] = Field(default_factory=list)
    reasons: list[ReasonOut] = Field(default_factory=list)
    sources: list[SourceOut] = Field(default_factory=list)
    text_direction: Literal["ltr", "rtl"] = "ltr"


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
    promise: str | None = None
    promise_date: date | None = None
    condition: str | None = None


class VerdictIn(BaseModel):
    verdict: Literal["resolved", "partial", "refused", "no_reply"]


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


class LanguageIn(BaseModel):
    language: str

    @field_validator("language")
    @classmethod
    def _bcp47(cls, v: str) -> str:
        return letter_language(v)


class SegmentOut(BaseModel):
    text: str
    kind: Literal["text", "fact", "blank"]
    key: str | None = None


class ReviewFactOut(BaseModel):
    key: str
    value: str
    display: list[str]
    confidence: float
    source_evidence_id: int | None
    source_filename: str | None
    used: bool


class CheckOut(BaseModel):
    id: str
    ok: bool
    detail: list[str] = Field(default_factory=list)


class ProblemOut(BaseModel):
    kind: str
    wrong: str
    expected: list[str]


class ReviewOut(BaseModel):
    message: MessageOut
    case_id: int
    language: str
    locale: str
    text_direction: Literal["ltr", "rtl"]
    subject_segments: list[SegmentOut]
    body_segments: list[SegmentOut]
    facts: list[ReviewFactOut]
    blanks: list[str]
    checks: list[CheckOut]
    problems: list[ProblemOut]
    can_approve: bool
    template_languages: list[str]
    step_name: str | None = None


class PreviewOut(BaseModel):
    language: str
    available: bool
    text_direction: Literal["ltr", "rtl"]
    subject: str | None = None
    body: str | None = None


class SettingsOut(BaseModel):
    llm_base_url: str
    model_smart: str
    model_fast: str
    has_llm_api_key: bool
    is_cloud: bool
    email_mode: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    has_smtp_password: bool
    default_country: str | None
    default_language: str
    enabled_letter_languages: list[str]
    demo_mode: bool
    version: str


class SettingsIn(BaseModel):
    """Only these keys can be changed from the web app; secrets are write-only."""

    llm_base_url: str | None = Field(default=None, pattern=r"^https?://")
    llm_api_key: str | None = None
    model_smart: str | None = None
    model_fast: str | None = None
    smtp_host: str | None = None
    smtp_port: int | None = Field(default=None, ge=1, le=65535)
    smtp_user: str | None = None
    smtp_app_password: str | None = None
    default_country: str | None = Field(default=None, pattern=r"^([A-Za-z]{2})?$")
    default_language: str | None = None

    @field_validator("default_language")
    @classmethod
    def _bcp47(cls, v: str | None) -> str | None:
        return letter_language(v) if v else None


class DemoOut(BaseModel):
    case_ids: list[int]
