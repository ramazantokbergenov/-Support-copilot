import os
import hashlib
import json
import re
import sqlite3
import uuid
from datetime import UTC, datetime
from urllib.parse import quote

from fastapi import FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from app.auth import (
    TOKEN_TTL_SECONDS,
    AuthenticationConfigurationError,
    AuthenticationError,
    issue_access_token,
    verify_access_token,
)
from app.ai_engine import AnalysisResult, SupportAnalysisEngine
from app.ai_engine.models import StructuredAnalysisResult
from app.database import (
    DEFAULT_DATABASE_PATH,
    IdempotencyConflictError,
    TicketRepository,
)
from app.models import (
    AnalysisSubmission,
    AccessTokenResponse,
    DecisionSubmission,
    DraftBody,
    ErrorDetail,
    ErrorResponse,
    LocalTokenSubmission,
    RuleList,
    RuleRecord,
    TicketDetail,
    TicketPriority,
    TicketStatus,
    TicketSummary,
    StatusUpdate,
    OperatorNoteSubmission,
)


MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_TOTAL_ATTACHMENT_BYTES = 25 * 1024 * 1024
MAX_ATTACHMENTS = 5
IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
ALLOWED_ATTACHMENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
    "text/plain",
}


def attachment_content_matches(content_type: str, content: bytes) -> bool:
    if content_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/webp":
        return content.startswith(b"RIFF") and content[8:12] == b"WEBP"
    if content_type == "application/pdf":
        return content.startswith(b"%PDF-")
    if content_type == "text/plain":
        try:
            content.decode("utf-8")
            return b"\x00" not in content
        except UnicodeDecodeError:
            return False
    return False


def ticket_request_hash(
    *,
    player_id: str,
    message: str,
    category: str | None,
    priority: str,
    attachments: list[dict],
) -> str:
    request_data = {
        "player_id": player_id,
        "message": message,
        "category": category,
        "priority": priority,
        "attachments": [
            {
                "filename": item["filename"],
                "content_type": item["content_type"],
                "sha256": hashlib.sha256(item["content"]).hexdigest(),
            }
            for item in attachments
        ],
    }
    canonical = json.dumps(request_data, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def create_app(repository: TicketRepository | None = None) -> FastAPI:
    application = FastAPI(
        title="ZHS Support Copilot API",
        version="0.1.0",
        description=(
            "Local ticket-management API. AI analysis is submitted by a separate "
            "trusted module; player-facing replies are never sent automatically."
        ),
    )
    allowed_origins = [
        origin.strip()
        for origin in os.environ.get(
            "ALLOWED_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    ]
    if not allowed_origins or "*" in allowed_origins:
        raise ValueError("ALLOWED_ORIGINS must contain explicit origins and cannot include '*'")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "Idempotency-Key"],
    )
    application.state.repository = repository

    def get_repository() -> TicketRepository:
        if application.state.repository is None:
            application.state.repository = TicketRepository(DEFAULT_DATABASE_PATH)
        return application.state.repository

    @application.middleware("http")
    async def require_bearer_token(request: Request, call_next):
        is_public_health = request.method == "GET" and request.url.path == "/health"
        is_public_login = request.method == "POST" and request.url.path == "/auth/token"
        if request.method == "OPTIONS" or is_public_health or is_public_login:
            return await call_next(request)

        authorization = request.headers.get("Authorization", "")
        scheme, separator, token = authorization.partition(" ")
        if not separator or scheme.casefold() != "bearer" or not token.strip():
            return _unauthorized_response()
        try:
            request.state.operator_id = verify_access_token(token.strip())
        except AuthenticationError:
            return _unauthorized_response()
        return await call_next(request)

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        _ = _request
        body = ErrorResponse(
            error=ErrorDetail(
                code="validation_error",
                message="Request validation failed",
                details=[
                    {
                        "location": ".".join(str(part) for part in error["loc"]),
                        "message": error["msg"],
                        "type": error["type"],
                    }
                    for error in exc.errors()
                ],
            )
        )
        return JSONResponse(
            content=body.model_dump(mode="json"),
            status_code=422,
        )

    @application.exception_handler(HTTPException)
    async def http_error_handler(
        _request: Request, exc: HTTPException
    ) -> JSONResponse:
        _ = _request
        if isinstance(exc.detail, dict):
            code = str(exc.detail.get("code", "request_error"))
            message = str(exc.detail.get("message", "Request failed"))
        else:
            code = "not_found" if exc.status_code == 404 else "request_error"
            message = str(exc.detail)
        body = ErrorResponse(error=ErrorDetail(code=code, message=message))
        return JSONResponse(
            content=body.model_dump(mode="json"),
            status_code=exc.status_code,
            headers=exc.headers,
        )

    @application.get("/health")
    def health() -> dict[str, str]:
        try:
            get_repository().health_check()
        except sqlite3.Error as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "database_unavailable",
                    "message": "The database is not available",
                },
            ) from exc
        return {"status": "ok"}

    @application.post("/auth/token", response_model=AccessTokenResponse)
    def create_access_token(credentials: LocalTokenSubmission) -> dict[str, str | int]:
        try:
            token = issue_access_token(credentials.username, credentials.password)
        except AuthenticationConfigurationError as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "authentication_unavailable",
                    "message": "Local operator authentication is not configured",
                },
            ) from exc
        except AuthenticationError as exc:
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "invalid_credentials",
                    "message": "Invalid username or password",
                },
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": TOKEN_TTL_SECONDS,
        }

    @application.post(
        "/tickets",
        response_model=TicketDetail,
        status_code=201,
        responses={413: {"model": ErrorResponse}},
    )
    async def create_ticket(
        player_id: str = Form(min_length=1, max_length=128),
        message: str = Form(min_length=1, max_length=20000),
        category: str | None = Form(default=None, max_length=100),
        priority: TicketPriority = Form(default=TicketPriority.NORMAL),
        attachments: list[UploadFile] | None = File(default=None),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        player_id = player_id.strip()
        message = message.strip()
        if not player_id or not message:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "validation_error",
                    "message": "player_id and message must not be blank",
                },
            )
        if idempotency_key is not None and not IDEMPOTENCY_KEY_PATTERN.fullmatch(
            idempotency_key
        ):
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "invalid_idempotency_key",
                    "message": "Idempotency-Key must be 8-128 safe characters",
                },
            )
        uploads = attachments or []
        if len(uploads) > MAX_ATTACHMENTS:
            raise HTTPException(
                status_code=413,
                detail={
                    "code": "too_many_attachments",
                    "message": f"At most {MAX_ATTACHMENTS} attachments are allowed",
                },
            )
        stored_attachments: list[dict] = []
        total_size = 0
        for upload in uploads:
            content = await upload.read(MAX_ATTACHMENT_BYTES + 1)
            if len(content) > MAX_ATTACHMENT_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail={
                        "code": "attachment_too_large",
                        "message": (
                            f"Each attachment must be at most "
                            f"{MAX_ATTACHMENT_BYTES} bytes"
                        ),
                    },
                )
            content_type = (upload.content_type or "application/octet-stream").split(";", 1)[0].strip().lower()
            if content_type not in ALLOWED_ATTACHMENT_TYPES:
                raise HTTPException(
                    status_code=415,
                    detail={
                        "code": "unsupported_file_type",
                        "message": "This attachment type is not allowed",
                    },
                )
            if not attachment_content_matches(content_type, content):
                raise HTTPException(
                    status_code=415,
                    detail={
                        "code": "invalid_file_content",
                        "message": "The attachment content does not match its declared type",
                    },
                )
            total_size += len(content)
            if total_size > MAX_TOTAL_ATTACHMENT_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail={
                        "code": "attachments_too_large",
                        "message": (
                            f"Combined attachments must be at most "
                            f"{MAX_TOTAL_ATTACHMENT_BYTES} bytes"
                        ),
                    },
                )
            stored_attachments.append(
                {
                    "attachment_id": str(uuid.uuid4()),
                    "filename": upload.filename or "attachment",
                    "content_type": content_type,
                    "size_bytes": len(content),
                    "content": content,
                }
            )
        normalized_category = category.strip() if category and category.strip() else None
        request_hash = (
            ticket_request_hash(
                player_id=player_id,
                message=message,
                category=normalized_category,
                priority=priority.value,
                attachments=stored_attachments,
            )
            if idempotency_key
            else None
        )
        try:
            ticket = get_repository().create_ticket(
                ticket_id=str(uuid.uuid4()),
                player_id=player_id,
                message=message,
                category=normalized_category,
                priority=priority.value,
                created_at=datetime.now(UTC).isoformat(),
                attachments=stored_attachments,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
            )
        except IdempotencyConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "idempotency_conflict",
                    "message": "Idempotency-Key was already used for a different request",
                },
            ) from exc
        return ticket

    @application.get("/tickets", response_model=list[TicketSummary])
    def list_tickets(
        status: TicketStatus | None = None,
        category: str | None = Query(default=None, max_length=100),
        priority: TicketPriority | None = None,
        q: str | None = Query(default=None, max_length=128),
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> list[dict]:
        return get_repository().list_tickets(
            status=status.value if status else None,
            category=category,
            priority=priority.value if priority else None,
            query=q,
            limit=limit,
            offset=offset,
        )

    @application.get(
        "/tickets/{ticket_id}",
        response_model=TicketDetail,
        responses={404: {"model": ErrorResponse}},
    )
    def get_ticket(ticket_id: str) -> dict:
        ticket = get_repository().get_ticket(ticket_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail="Ticket not found")
        return ticket

    @application.patch(
        "/tickets/{ticket_id}/status",
        response_model=TicketSummary,
        responses={404: {"model": ErrorResponse}},
    )
    def update_ticket_status(ticket_id: str, update: StatusUpdate) -> dict:
        repository = get_repository()
        if not repository.update_status(ticket_id, update.status.value):
            raise HTTPException(status_code=404, detail="Ticket not found")
        ticket = repository.get_ticket(ticket_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail="Ticket not found")
        return ticket

    @application.post(
        "/tickets/{ticket_id}/analysis",
        response_model=TicketDetail,
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def submit_analysis(ticket_id: str, analysis: AnalysisSubmission) -> dict:
        try:
            repository = get_repository()
            saved = repository.save_analysis(
                ticket_id, analysis.model_dump(mode="json")
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "unknown_rule", "message": str(exc)},
            ) from exc
        if not saved:
            raise HTTPException(status_code=404, detail="Ticket not found")
        ticket = repository.get_ticket(ticket_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail="Ticket not found")
        return ticket

    @application.post(
        "/tickets/{ticket_id}/analyze",
        response_model=AnalysisResult,
        responses={404: {"model": ErrorResponse}},
    )
    def analyze_ticket(ticket_id: str) -> AnalysisResult:
        repository = get_repository()
        ticket = repository.get_ticket(ticket_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail="Ticket not found")

        result = SupportAnalysisEngine(repository).analyze(ticket)
        extracted_facts = [
            *(f"PLAYER_CLAIMS: {claim}" for claim in result.player_claims),
            *(
                f"ATTACHMENTS: {item.filename} "
                f"({item.content_type}, {item.size_bytes} bytes; not inspected)"
                for item in result.attachments
            ),
            *(
                f"VERIFIED_SYSTEM_DATA: {fact}"
                for fact in result.verified_system_data
            ),
            *(f"UNKNOWN: {unknown}" for unknown in result.unknowns),
        ]
        saved = repository.save_analysis(
            ticket_id,
            {
                "category": result.category.value,
                "priority": ticket["priority"],
                "extracted_facts": extracted_facts,
                "matched_rules": [
                    {
                        "document_name": rule.document_name,
                        "rule_id": rule.rule_id,
                    }
                    for rule in result.matched_rules
                ],
                "draft_reply": result.draft_reply,
                "confidence": result.confidence,
                "escalation_required": result.escalation_required,
                "escalation_reason": result.escalation_reason or None,
                "ai_analysis": result.model_dump(mode="json"),
            },
        )
        if not saved:
            raise HTTPException(status_code=404, detail="Ticket not found")
        return result

    @application.post(
        "/tickets/{ticket_id}/analyze-structured",
        response_model=StructuredAnalysisResult,
        responses={404: {"model": ErrorResponse}},
    )
    def analyze_ticket_structured(ticket_id: str) -> StructuredAnalysisResult:
        repository = get_repository()
        ticket = repository.get_ticket(ticket_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail="Ticket not found")

        engine = SupportAnalysisEngine(repository)
        structured, _model_name = engine.analyze_structured(ticket)
        legacy = engine.to_legacy_result(structured)
        extracted_facts = [
            *(f"PLAYER_CLAIMS: {claim}" for claim in structured.player_claims),
            *(
                f"ATTACHMENTS: {item.filename} "
                f"({item.content_type}, {item.size_bytes} bytes; not inspected)"
                for item in structured.provided_evidence
            ),
            *(f"VERIFIED_SYSTEM_DATA: {fact}" for fact in structured.verified_data),
            *(f"UNKNOWN: {unknown}" for unknown in structured.unknowns),
        ]
        try:
            saved = repository.save_analysis(
                ticket_id,
                {
                    "category": legacy.category.value,
                    "priority": ticket["priority"],
                    "extracted_facts": extracted_facts,
                    "matched_rules": [
                        {"document_name": item.document_title, "rule_id": item.rule_number}
                        for item in structured.rule_references
                    ],
                    "draft_reply": structured.draft_reply,
                    "confidence": structured.confidence,
                    "escalation_required": structured.human_review_required,
                    "escalation_reason": " ".join(structured.escalation_reasons) or None,
                    "ai_analysis": {
                        **legacy.model_dump(mode="json"),
                        **structured.model_dump(mode="json"),
                        "category_reason": structured.analysis,
                        "attachments": [
                            {
                                **item.model_dump(mode="json"),
                                "inspected": False,
                            }
                            for item in structured.provided_evidence
                        ],
                        "verified_system_data": structured.verified_data,
                        "matched_rules": legacy.model_dump(mode="json")["matched_rules"],
                        "escalation_required": structured.human_review_required,
                        "escalation_reason": " ".join(structured.escalation_reasons) or None,
                    },
                },
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "unknown_rule", "message": str(exc)},
            ) from exc
        if not saved:
            raise HTTPException(status_code=404, detail="Ticket not found")
        return structured

    @application.post(
        "/tickets/{ticket_id}/generate-reply",
        status_code=201,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def generate_reply(ticket_id: str) -> dict:
        repository = get_repository()
        ticket = repository.get_ticket(ticket_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail="Ticket not found")
        if ticket.get("ai_analysis") is None:
            raise HTTPException(
                status_code=409,
                detail={"code": "analysis_required", "message": "Analyze the ticket before generating a reply."},
            )
        structured, model_name = SupportAnalysisEngine(repository).analyze_structured(ticket)
        draft = repository.save_draft(
            ticket_id,
            structured.draft_reply,
            draft_id=None,
            operator_id="local-operator",
            now=datetime.now(UTC).isoformat(),
        )
        if draft is None:
            raise HTTPException(status_code=404, detail="Ticket not found")
        return {**draft, "model_name": model_name}

    @application.post(
        "/tickets/{ticket_id}/drafts",
        status_code=201,
        responses={404: {"model": ErrorResponse}},
    )
    def create_draft(ticket_id: str, draft: DraftBody) -> dict:
        saved = get_repository().save_draft(
            ticket_id,
            draft.body,
            draft_id=None,
            operator_id="local-operator",
            now=datetime.now(UTC).isoformat(),
        )
        if saved is None:
            raise HTTPException(status_code=404, detail="Ticket not found")
        return saved

    @application.put(
        "/tickets/{ticket_id}/drafts/{draft_id}",
        responses={404: {"model": ErrorResponse}},
    )
    def update_draft(ticket_id: str, draft_id: str, draft: DraftBody) -> dict:
        saved = get_repository().save_draft(
            ticket_id,
            draft.body,
            draft_id=draft_id,
            operator_id="local-operator",
            now=datetime.now(UTC).isoformat(),
        )
        if saved is None:
            raise HTTPException(status_code=404, detail="Draft or ticket not found")
        return saved

    @application.post(
        "/tickets/{ticket_id}/decisions",
        status_code=201,
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def record_decision(ticket_id: str, decision: DecisionSubmission) -> dict:
        allowed = {"mark_reviewed", "unmark_reviewed", "approve", "reject", "escalate", "request_information"}
        if decision.decision not in allowed:
            raise HTTPException(status_code=422, detail="Invalid operator decision")
        result = get_repository().record_decision(
            ticket_id,
            decision.decision,
            draft_id=decision.draft_id,
            note=decision.note,
            operator_id="local-operator",
            now=datetime.now(UTC).isoformat(),
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Ticket or draft not found")
        return result

    @application.post(
        "/tickets/{ticket_id}/notes",
        status_code=201,
        responses={404: {"model": ErrorResponse}},
    )
    def add_operator_note(ticket_id: str, note: OperatorNoteSubmission) -> dict:
        result = get_repository().add_operator_note(
            ticket_id,
            note.body,
            operator_id="local-operator",
            note_id=str(uuid.uuid4()),
            now=datetime.now(UTC).isoformat(),
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Ticket not found")
        return result

    @application.get(
        "/tickets/{ticket_id}/events",
        responses={404: {"model": ErrorResponse}},
    )
    def list_ticket_events(
        ticket_id: str,
        limit: int = Query(default=50, ge=1, le=100),
    ) -> list[dict]:
        result = get_repository().list_ticket_events(ticket_id, limit)
        if result is None:
            raise HTTPException(status_code=404, detail="Ticket not found")
        return result

    @application.get(
        "/tickets/{ticket_id}/attachments/{attachment_id}",
        responses={404: {"model": ErrorResponse}},
    )
    def get_attachment(ticket_id: str, attachment_id: str) -> Response:
        attachment = get_repository().get_attachment(ticket_id, attachment_id)
        if attachment is None:
            raise HTTPException(status_code=404, detail="Attachment not found")
        filename = quote(attachment["filename"], safe="")
        return Response(
            content=attachment["content"],
            media_type=attachment["content_type"],
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @application.get("/rules", response_model=RuleList)
    def list_rules(
        query: str | None = Query(default=None, max_length=200),
        language: str | None = Query(default=None, max_length=20),
        limit: int = Query(default=50, ge=1, le=100),
    ) -> dict:
        items = get_repository().list_rules(
            query=query, language=language, limit=limit
        )
        validated_items = [RuleRecord.model_validate(item) for item in items]
        return {"items": validated_items, "count": len(validated_items)}

    return application


def _unauthorized_response() -> JSONResponse:
    body = ErrorResponse(
        error=ErrorDetail(
            code="unauthorized",
            message="A valid bearer token is required",
        )
    )
    return JSONResponse(
        content=body.model_dump(mode="json"),
        status_code=401,
        headers={"WWW-Authenticate": "Bearer"},
    )


app = create_app()
