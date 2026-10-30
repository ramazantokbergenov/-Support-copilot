from datetime import datetime
from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, model_validator


ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class TicketStatus(str, Enum):
    NEW = "New"
    PROCESSING = "Processing"
    NEEDS_REVIEW = "Needs Review"
    APPROVED = "Approved"
    ESCALATED = "Escalated"
    CLOSED = "Closed"


class TicketPriority(str, Enum):
    LOW = "Low"
    NORMAL = "Normal"
    HIGH = "High"
    URGENT = "Urgent"


class RuleReference(BaseModel):
    document_name: ShortText
    rule_id: ShortText


class RuleRecord(RuleReference):
    rule_title: ShortText
    rule_text: ShortText
    source_url: HttpUrl
    language: ShortText
    version_or_date: str | None = None


class AttachmentRecord(BaseModel):
    attachment_id: str
    filename: str
    content_type: str
    size_bytes: int


class TicketSummary(BaseModel):
    ticket_id: str
    player_id: str
    category: str | None
    priority: TicketPriority
    status: TicketStatus
    confidence: float | None
    escalation_required: bool | None
    created_at: datetime


class TicketDetail(TicketSummary):
    message: str
    attachments: list[AttachmentRecord]
    extracted_facts: list[str] | None
    matched_rules: list[RuleRecord]
    draft_reply: str | None
    escalation_reason: str | None
    ai_analysis: dict[str, Any] | None = None


class AnalysisSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: ShortText
    priority: TicketPriority
    extracted_facts: list[ShortText]
    matched_rules: list[RuleReference]
    draft_reply: ShortText
    confidence: float = Field(ge=0, le=1)
    escalation_required: bool
    escalation_reason: str | None = None

    @model_validator(mode="after")
    def validate_escalation_reason(self) -> "AnalysisSubmission":
        if self.escalation_required and not (self.escalation_reason or "").strip():
            raise ValueError("escalation_reason is required when escalation_required is true")
        return self


class StatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: TicketStatus


class RuleList(BaseModel):
    items: list[RuleRecord]
    count: int


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: list[dict[str, object]] | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
