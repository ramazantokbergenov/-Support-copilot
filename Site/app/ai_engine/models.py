from enum import Enum

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
