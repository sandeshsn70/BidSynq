"""Request and response schemas.

Response models double as the API contract the frontend is tested against
(see tests/test_frontend_contract.py), so every field returned to the browser is declared here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, computed_field, field_validator

# --------------------------------------------------------------------------- auth


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Literal["buyer", "supplier", "admin"] = "supplier"
    company_name: str = Field(default="", max_length=180)

    @field_validator("name", "company_name")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if len(value) < 2:
            raise ValueError("Name must contain at least 2 characters")
        return value


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    name: str
    # Plain str (not EmailStr): rows created by older versions must never break a response.
    email: str
    role: str
    company_name: str

    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------------------------ tenders


class TenderCreate(BaseModel):
    title: str = Field(min_length=4, max_length=200)
    description: str = Field(default="", max_length=10000)
    category: str = Field(default="General", max_length=100)
    quantity: int = Field(default=1, ge=1, le=1_000_000_000)
    tender_type: Literal["rfq", "sealed", "reverse_auction"] = "rfq"
    deadline: datetime
    mandatory_requirements: str = Field(default="", max_length=5000)

    w_price: float = Field(default=0.35, ge=0, le=1, allow_inf_nan=False)
    w_delivery: float = Field(default=0.20, ge=0, le=1, allow_inf_nan=False)
    w_trust: float = Field(default=0.25, ge=0, le=1, allow_inf_nan=False)
    w_match: float = Field(default=0.20, ge=0, le=1, allow_inf_nan=False)

    anti_sniping: bool = True

    @field_validator("title", "category", "description", "mandatory_requirements")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        if len(value) < 4:
            raise ValueError("Title must contain at least 4 non-whitespace characters")
        return value

    @field_validator("category")
    @classmethod
    def default_category(cls, value: str) -> str:
        return value or "General"

    @field_validator("deadline")
    @classmethod
    def validate_deadline(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Deadline must include a timezone, for example +05:30 or Z")
        return value


class TenderUpdate(BaseModel):
    """Partial update. tender_type can never change after creation."""

    title: str | None = Field(default=None, min_length=4, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    quantity: int | None = Field(default=None, ge=1, le=1_000_000_000)
    deadline: datetime | None = None
    mandatory_requirements: str | None = Field(default=None, max_length=5000)
    w_price: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    w_delivery: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    w_trust: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    w_match: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    anti_sniping: bool | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("title", "category", "description", "mandatory_requirements")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value

    @field_validator("deadline")
    @classmethod
    def validate_deadline(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("Deadline must include a timezone, for example +05:30 or Z")
        return value


class TenderOut(BaseModel):
    id: int
    buyer_id: int
    title: str
    description: str
    category: str
    quantity: int
    tender_type: str
    deadline: datetime
    status: str
    mandatory_requirements: str
    w_price: float
    w_delivery: float
    w_trust: float
    w_match: float
    anti_sniping: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def bidding_open(self) -> bool:
        """True while the tender is open AND its deadline has not passed."""
        deadline = self.deadline if self.deadline.tzinfo else self.deadline.replace(tzinfo=timezone.utc)
        return self.status == "open" and deadline > datetime.now(timezone.utc)


class TenderStatusUpdate(BaseModel):
    status: Literal["closed", "cancelled"]


# ---------------------------------------------------------------------------- bids


class BidCreate(BaseModel):
    price: float = Field(gt=0, le=1e13, allow_inf_nan=False)
    delivery_days: int = Field(ge=1, le=3650)
    validity_days: int = Field(default=30, ge=1, le=365)
    requirement_match: float = Field(default=100, ge=0, le=100, allow_inf_nan=False)
    mandatory_met: bool = True
    compliance_notes: str = Field(default="", max_length=5000)

    @field_validator("compliance_notes")
    @classmethod
    def strip_compliance_notes(cls, value: str) -> str:
        return value.strip()


class BidOut(BaseModel):
    id: int
    tender_id: int
    supplier_id: int
    price: float
    delivery_days: int
    validity_days: int
    requirement_match: float
    mandatory_met: bool
    compliance_notes: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BidDetailOut(BidOut):
    supplier_name: str | None = None
    supplier_company: str | None = None


class MyBidOut(BidOut):
    tender_title: str
    tender_status: str
    tender_type: str
    tender_deadline: datetime
    bidding_open: bool


class RankedBidOut(BaseModel):
    bid_id: int | None = None
    supplier_id: int | None = None
    supplier_company: str | None = None
    eligible: bool
    score: float
    price_score: float | None = None
    delivery_score: float | None = None
    trust_score: float | None = None
    requirement_match: float | None = None
    reason_codes: list[str]
    explanation: list[str] = []


class RankingOut(BaseModel):
    tender_id: int
    weights: dict[str, float]
    method: str
    ranking: list[RankedBidOut]
    note: str


class DashboardOut(BaseModel):
    role: str
    tenders: int | None = None
    open_tenders: int
    bids_received: int | None = None
    open_risk_alerts: int | None = None
    submitted_bids: int | None = None


# ------------------------------------------------------------- documents and RAG


class DocumentOut(BaseModel):
    id: int
    tender_id: int
    filename: str
    file_type: str
    file_size: int
    status: str
    created_at: datetime


class UploadOut(DocumentOut):
    chunks_indexed: int


class DeleteOut(BaseModel):
    status: str
    document_id: int


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=1200)

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Question must contain at least 3 characters")
        return value


class CitationOut(BaseModel):
    source_id: str
    document_id: int
    filename: str
    page_number: int | None = None
    section: str
    excerpt: str
    relevance_score: float


class AskOut(BaseModel):
    answer: str
    mode: str
    citations: list[CitationOut]
    disclaimer: str
    notice: str | None = None


class ChecklistEvidenceOut(BaseModel):
    filename: str
    page_number: int | None = None
    excerpt: str


class ChecklistItemOut(BaseModel):
    requirement: str
    evidence_found: bool
    evidence: ChecklistEvidenceOut | None = None
    review_status: str


class ChecklistOut(BaseModel):
    tender_id: int
    checklist: list[ChecklistItemOut]
    note: str


# --------------------------------------------------- supplier / price intelligence


class SupplierOutcomeIn(BaseModel):
    supplier_id: int = Field(gt=0)
    quality_score: float = Field(ge=1, le=5, allow_inf_nan=False)
    on_time: bool
    issue_count: int = Field(default=0, ge=0, le=100)
    notes: str = Field(default="", max_length=2000)

    @field_validator("notes")
    @classmethod
    def strip_notes(cls, value: str) -> str:
        return value.strip()


class OutcomeOut(BaseModel):
    id: int
    tender_id: int
    supplier_id: int
    quality_score: float
    on_time: bool
    issue_count: int
    created_at: datetime
    message: str


class RecentOutcomeOut(BaseModel):
    tender_id: int
    quality_score: float
    on_time: bool
    issue_count: int
    created_at: datetime


class TrustOut(BaseModel):
    supplier_id: int
    company_name: str
    score: float
    confidence: str
    observations: int
    components: dict[str, float | None]
    explanation: str
    recent_outcomes: list[RecentOutcomeOut]


class SimilarMatchOut(BaseModel):
    tender_id: int | None = None
    title: str
    category: str
    quantity: int
    similarity: float
    status: str
    created_at: str | None = None


class SimilarOut(BaseModel):
    tender_id: int
    matches: list[SimilarMatchOut]
    method: str
    note: str


class PriceRangeOut(BaseModel):
    low: float
    high: float


class PriceOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    tender_id: int
    category: str
    quantity: int
    currency: str
    predicted_total_price: float | None = None
    suggested_range: PriceRangeOut | None = None
    model: str | None = None
    training_samples: int
    same_category_samples: int
    source: str
    explanation: str
    model_note: str | None = None
    feature_importance: str | None = None
    human_review_required: bool
    disclaimer: str


# ------------------------------------------------------------------ risk and audit


class RiskAlertOut(BaseModel):
    id: int
    tender_id: int
    bid_id: int | None = None
    rule_key: str
    severity: str
    title: str
    explanation: str
    evidence: dict[str, Any]
    status: str
    review_note: str
    created_at: datetime
    reviewed_at: datetime | None = None


class ScanOut(BaseModel):
    tender_id: int
    bids_checked: int
    signals_detected: int
    new_alerts_saved: int
    alerts: list[RiskAlertOut]
    disclaimer: str


class ReviewIn(BaseModel):
    status: Literal["reviewed", "dismissed"]
    note: str = Field(default="", max_length=2000)

    @field_validator("note")
    @classmethod
    def strip_note(cls, value: str) -> str:
        return value.strip()


class ReviewOut(BaseModel):
    id: int
    status: str
    review_note: str
    reviewed_at: datetime | None = None


class AuditItemOut(BaseModel):
    id: int
    actor_id: int | None = None
    action: str
    entity_type: str
    entity_id: str
    details: dict[str, Any]
    previous_hash: str
    entry_hash: str
    created_at: datetime


class AuditPageOut(BaseModel):
    items: list[AuditItemOut]
    limit: int
    offset: int


class VerifyOut(BaseModel):
    valid: bool
    checked_entries: int
    head_hash: str | None = None
    last_entry_id: int | None = None
    broken_at_id: int | None = None
    reason: str | None = None
    note: str


class HealthOut(BaseModel):
    status: str
    version: str
    database: str
    migration_revision: str | None = None
    rag: str
    groq_configured: bool
    supplier_intelligence: str
    price_intelligence: str
    risk_monitoring: str
    audit_chain: str
