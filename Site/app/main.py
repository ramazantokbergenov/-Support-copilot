import uuid
from datetime import UTC, datetime
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from app.ai_engine import AnalysisResult, SupportAnalysisEngine
from app.database import DEFAULT_DATABASE_PATH, TicketRepository
from app.models import (
    AnalysisSubmission,
    ErrorDetail,
    ErrorResponse,
    RuleList,
    RuleRecord,
    TicketDetail,
    TicketPriority,
    TicketStatus,
    TicketSummary,
    StatusUpdate,
)


MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_TOTAL_ATTACHMENT_BYTES = 25 * 1024 * 1024
MAX_ATTACHMENTS = 5


def create_app(repository: TicketRepository | None = None) -> FastAPI:
    application = FastAPI(
        title="ZHS Support Copilot API",
        version="0.1.0",
        description=(
            "Local ticket-management API. AI analysis is submitted by a separate "
            "trusted module; player-facing replies are never sent automatically."
        ),
    )
    application.state.repository = repository

    def get_repository() -> TicketRepository:
        if application.state.repository is None:
            application.state.repository = TicketRepository(DEFAULT_DATABASE_PATH)
        return application.state.repository

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
        return {"status": "ok"}

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
                    "content_type": upload.content_type or "application/octet-stream",
                    "size_bytes": len(content),
                    "content": content,
                }
            )
        ticket = get_repository().create_ticket(
            ticket_id=str(uuid.uuid4()),
            player_id=player_id,
            message=message,
            category=category.strip() if category and category.strip() else None,
            priority=priority.value,
            created_at=datetime.now(UTC).isoformat(),
            attachments=stored_attachments,
        )
        return ticket

    @application.get("/tickets", response_model=list[TicketSummary])
    def list_tickets(
        status: TicketStatus | None = None,
        category: str | None = Query(default=None, max_length=100),
        priority: TicketPriority | None = None,
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> list[dict]:
        return get_repository().list_tickets(
            status=status.value if status else None,
            category=category,
            priority=priority.value if priority else None,
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


app = create_app()
