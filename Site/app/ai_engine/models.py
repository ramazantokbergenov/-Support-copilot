from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints
from typing import Annotated


NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class TicketCategory(str, Enum):
    APPEAL_BAN = "Appeal / Ban"
    PLAYER_REPORT = "Player Report"
    ADMIN_COMPLAINT = "Admin Complaint"
    ACCOUNT_SECURITY = "Account Security"
    PAYMENT_PURCHASE = "Payment / Purchase"
    BUG_TECHNICAL = "Bug / Technical Issue"
    OTHER_UNCLEAR = "Other / Unclear"


class AttachmentEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attachment_id: str
    filename: str
    content_type: str
    size_bytes: int = Field(ge=0)
    inspected: bool = False


class MatchedRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_name: NonEmptyText
    rule_id: NonEmptyText
    rule_title: NonEmptyText
    excerpt: NonEmptyText
    source_url: HttpUrl
    language: NonEmptyText
    version_or_date: str | None = None


class AnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: TicketCategory
    category_reason: NonEmptyText
    language: NonEmptyText
    summary: NonEmptyText
    player_claims: list[NonEmptyText]
    attachments: list[AttachmentEvidence]
    verified_system_data: list[NonEmptyText]
    unknowns: list[NonEmptyText]
    matched_rules: list[MatchedRule]
    draft_reply: NonEmptyText
    confidence: float = Field(ge=0, le=1)
    escalation_required: bool
    escalation_reason: str


class SupportLanguage(str, Enum):
    RU = "ru"
    KK = "kk"
    UZ = "uz"
    OTHER = "other"


class SupportCategory(str, Enum):
    APPEAL_BAN = "appeal_ban"
    PLAYER_REPORT = "player_report"
    ADMIN_COMPLAINT = "admin_complaint"
    ACCOUNT_SECURITY = "account_security"
    PAYMENT = "payment"
    BUG = "bug"
    OTHER = "other"


class SupportPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class ProvidedEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attachment_id: NonEmptyText
    filename: NonEmptyText
    content_type: NonEmptyText
    size_bytes: int = Field(ge=0)


class OfficialRuleReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_title: NonEmptyText
    rule_number: NonEmptyText
    exact_excerpt: NonEmptyText
    source_url: HttpUrl
    source_version_date: NonEmptyText


class StructuredAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket_id: NonEmptyText
    language: SupportLanguage
    category: SupportCategory
    priority: SupportPriority
    summary: NonEmptyText
    player_claims: list[NonEmptyText]
    provided_evidence: list[ProvidedEvidence]
    verified_data: list[NonEmptyText]
    unknowns: list[NonEmptyText]
    missing_information_questions: list[NonEmptyText]
    rule_references: list[OfficialRuleReference]
    analysis: NonEmptyText
    draft_reply: NonEmptyText
    human_review_required: bool
    escalation_reasons: list[NonEmptyText]
    confidence: float = Field(ge=0, le=1)
