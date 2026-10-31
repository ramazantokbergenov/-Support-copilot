import asyncio
import os
import secrets
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from app.database import TicketRepository
from app.main import create_app


class TicketApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repository = TicketRepository(Path(self.temp_dir.name) / "test.db")
        self.auth_password = secrets.token_urlsafe(24)
        self.auth_environment = patch.dict(
            os.environ,
            {
                "SUPPORT_COPILOT_AUTH_SECRET": secrets.token_urlsafe(48),
                "SUPPORT_COPILOT_OPERATOR_USERNAME": "test-operator",
                "SUPPORT_COPILOT_OPERATOR_PASSWORD": self.auth_password,
            },
        )
        self.auth_environment.start()
        self.app = create_app(self.repository)
        transport = httpx.ASGITransport(app=self.app)
        self.client = httpx.AsyncClient(transport=transport, base_url="http://test")
        token_response = await self.client.post(
            "/auth/token",
            json={"username": "test-operator", "password": self.auth_password},
        )
        self.assertEqual(token_response.status_code, 200, token_response.text)
        self.client.headers["Authorization"] = f"Bearer {token_response.json()['access_token']}"

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self.temp_dir.cleanup()
        self.auth_environment.stop()

    async def test_ticket_routes_require_valid_bearer_authentication(self) -> None:
        anonymous = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://test"
        )
        try:
            missing_token = await anonymous.get("/tickets")
            invalid_token = await anonymous.get(
                "/tickets", headers={"Authorization": "Bearer invalid.token.value"}
            )
            unauthorized_create = await anonymous.post(
                "/tickets",
                data={"player_id": "unauthorized", "message": "Must be rejected"},
            )
            await self.create_ticket()
            ticket_id = (await self.client.get("/tickets")).json()[0]["ticket_id"]
            unauthorized_update = await anonymous.patch(
                f"/tickets/{ticket_id}/status", json={"status": "Closed"}
            )
            ticket_details = await self.client.get(f"/tickets/{ticket_id}")
            health = await anonymous.get("/health")
        finally:
            await anonymous.aclose()

        self.assertEqual(missing_token.status_code, 401)
        self.assertEqual(invalid_token.status_code, 401)
        self.assertEqual(unauthorized_create.status_code, 401)
        self.assertEqual(unauthorized_update.status_code, 401)
        self.assertEqual(ticket_details.json()["status"], "New")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json(), {"status": "ok"})

    async def test_invalid_local_login_does_not_issue_a_token(self) -> None:
        response = await self.client.post(
            "/auth/token", json={"username": "test-operator", "password": "wrong"}
        )
        unicode_password = await self.client.post(
            "/auth/token",
            json={"username": "test-operator", "password": "пароль-неверный"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "invalid_credentials")
        self.assertEqual(unicode_password.status_code, 401)
        self.assertEqual(unicode_password.json()["error"]["code"], "invalid_credentials")

    async def create_ticket(
        self,
        *,
        files: list[tuple[str, tuple]] | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        headers = (
            {"Idempotency-Key": idempotency_key} if idempotency_key else None
        )
        response = await self.client.post(
            "/tickets",
            data={"player_id": "player-1", "message": "Please review this report"},
            files=files,
            headers=headers,
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    async def test_ticket_creation_is_idempotent(self) -> None:
        headers = {"Idempotency-Key": "qa-ticket-create-0001"}
        payload = {"player_id": "player-idempotent", "message": "Same request"}
        first = await self.client.post("/tickets", data=payload, headers=headers)
        repeated = await self.client.post("/tickets", data=payload, headers=headers)
        different_payload = await self.client.post(
            "/tickets",
            data={"player_id": "player-idempotent", "message": "Changed request"},
            headers=headers,
        )
        listed = await self.client.get("/tickets?q=player-idempotent")

        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(repeated.status_code, 201, repeated.text)
        self.assertEqual(first.json()["ticket_id"], repeated.json()["ticket_id"])
        self.assertEqual(different_payload.status_code, 409)
        self.assertEqual(different_payload.json()["error"]["code"], "idempotency_conflict")
        self.assertEqual(len(listed.json()), 1)

    async def test_concurrent_ticket_creation_with_same_key_is_idempotent(self) -> None:
        headers = {"Idempotency-Key": "qa-ticket-concurrent-0001"}
        payload = {"player_id": "player-concurrent", "message": "Concurrent request"}
        responses = await asyncio.gather(
            *(
                self.client.post("/tickets", data=payload, headers=headers)
                for _ in range(5)
            )
        )

        self.assertTrue(all(response.status_code == 201 for response in responses))
        ticket_ids = {response.json()["ticket_id"] for response in responses}
        self.assertEqual(len(ticket_ids), 1)
        listed = await self.client.get("/tickets?q=player-concurrent")
        self.assertEqual(len(listed.json()), 1)

    async def test_idempotency_key_validation_and_cors(self) -> None:
        invalid_key = await self.client.post(
            "/tickets",
            data={"player_id": "player-1", "message": "Invalid key"},
            headers={"Idempotency-Key": "short"},
        )
        preflight = await self.client.options(
            "/tickets",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type,idempotency-key",
            },
        )

        self.assertEqual(invalid_key.status_code, 422)
        self.assertEqual(preflight.status_code, 200)
        self.assertIn("idempotency-key", preflight.headers["access-control-allow-headers"].casefold())

    async def test_cors_configuration_rejects_wildcard_origin(self) -> None:
        with patch.dict(os.environ, {"ALLOWED_ORIGINS": "*"}):
            with self.assertRaisesRegex(ValueError, "explicit origins"):
                create_app(self.repository)

    async def test_create_list_status_and_details(self) -> None:
        ticket = await self.create_ticket()
        ticket_id = ticket["ticket_id"]

        self.assertEqual(ticket["status"], "New")
        self.assertEqual(ticket["attachments"], [])
        self.assertIsNone(ticket["confidence"])

        listed = await self.client.get("/tickets?status=New")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual([item["ticket_id"] for item in listed.json()], [ticket_id])

        updated = await self.client.patch(
            f"/tickets/{ticket_id}/status", json={"status": "Processing"}
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["status"], "Processing")

        details = await self.client.get(f"/tickets/{ticket_id}")
        self.assertEqual(details.status_code, 200)
        self.assertEqual(details.json()["message"], "Please review this report")

    async def test_health_check(self) -> None:
        response = await self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    async def test_health_check_reports_database_failure(self) -> None:
        class UnavailableRepository:
            def health_check(self) -> None:
                raise sqlite3.OperationalError("database is unavailable")

        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(UnavailableRepository())),
            base_url="http://test",
        )
        try:
            response = await client.get("/health")
        finally:
            await client.aclose()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "database_unavailable")

    async def test_invalid_and_missing_status_updates_are_rejected(self) -> None:
        ticket = await self.create_ticket()
        ticket_id = ticket["ticket_id"]

        invalid = await self.client.patch(
            f"/tickets/{ticket_id}/status", json={"status": "Unknown"}
        )
        missing = await self.client.patch(
            "/tickets/missing/status", json={"status": "Processing"}
        )
        unchanged = await self.client.get(f"/tickets/{ticket_id}")

        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(unchanged.json()["status"], "New")

    async def test_reply_generation_requires_analysis(self) -> None:
        ticket = await self.create_ticket()
        response = await self.client.post(
            f"/tickets/{ticket['ticket_id']}/generate-reply", json={}
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "analysis_required")

    async def test_ticket_search_matches_player_and_message(self) -> None:
        await self.create_ticket()
        by_player = await self.client.get("/tickets?q=player-1")
        by_message = await self.client.get("/tickets?q=review%20this%20report")
        no_match = await self.client.get("/tickets?q=missing-player")
        injection_like = await self.client.get("/tickets", params={"q": "' OR 1=1 --"})

        self.assertEqual(len(by_player.json()), 1)
        self.assertEqual(len(by_message.json()), 1)
        self.assertEqual(no_match.json(), [])
        self.assertEqual(injection_like.json(), [])

    async def test_draft_decision_note_and_event_flow(self) -> None:
        ticket = await self.create_ticket()
        ticket_id = ticket["ticket_id"]

        created = await self.client.post(
            f"/tickets/{ticket_id}/drafts",
            json={"body": "Черновик для проверки оператором."},
        )
        self.assertEqual(created.status_code, 201, created.text)
        draft = created.json()
        self.assertEqual(draft["version"], 1)

        edited = await self.client.put(
            f"/tickets/{ticket_id}/drafts/{draft['id']}",
            json={"body": "Исправленный черновик для проверки оператором."},
        )
        self.assertEqual(edited.status_code, 200, edited.text)
        self.assertEqual(edited.json()["body"], "Исправленный черновик для проверки оператором.")

        reviewed = await self.client.post(
            f"/tickets/{ticket_id}/decisions",
            json={"decision": "mark_reviewed", "draft_id": draft["id"]},
        )
        self.assertEqual(reviewed.status_code, 201, reviewed.text)
        detail = await self.client.get(f"/tickets/{ticket_id}")
        self.assertEqual(detail.json()["draft_status"], "reviewed")
        self.assertEqual(detail.json()["draft_reply"], "Исправленный черновик для проверки оператором.")

        note = await self.client.post(
            f"/tickets/{ticket_id}/notes",
            json={"body": "Проверить дату обращения."},
        )
        self.assertEqual(note.status_code, 201, note.text)
        updated_detail = await self.client.get(f"/tickets/{ticket_id}")
        self.assertEqual(updated_detail.json()["operator_notes"][0]["body"], "Проверить дату обращения.")

        events = await self.client.get(f"/tickets/{ticket_id}/events")
        self.assertEqual(events.status_code, 200)
        self.assertGreaterEqual(len(events.json()), 3)
        self.assertIn("operator.mark_reviewed", [item["action"] for item in events.json()])

    async def test_draft_decision_note_and_event_workflow(self) -> None:
        ticket = await self.create_ticket()
        ticket_id = ticket["ticket_id"]
        analyzed = await self.client.post(f"/tickets/{ticket_id}/analyze-structured")
        self.assertEqual(analyzed.status_code, 200, analyzed.text)

        generated = await self.client.post(f"/tickets/{ticket_id}/generate-reply", json={})
        self.assertEqual(generated.status_code, 201, generated.text)
        draft = generated.json()
        self.assertTrue(draft["body"])

        edited = await self.client.put(
            f"/tickets/{ticket_id}/drafts/{draft['id']}",
            json={"body": "Operator edited draft."},
        )
        self.assertEqual(edited.status_code, 200, edited.text)
        self.assertEqual(edited.json()["body"], "Operator edited draft.")

        reviewed = await self.client.post(
            f"/tickets/{ticket_id}/decisions",
            json={"decision": "mark_reviewed", "draft_id": draft["id"]},
        )
        self.assertEqual(reviewed.status_code, 201, reviewed.text)
        details = await self.client.get(f"/tickets/{ticket_id}")
        self.assertEqual(details.json()["draft_status"], "reviewed")
        self.assertEqual(details.json()["draft_reply"], "Operator edited draft.")

        note = await self.client.post(
            f"/tickets/{ticket_id}/notes", json={"body": "Internal review note."}
        )
        self.assertEqual(note.status_code, 201, note.text)
        details = await self.client.get(f"/tickets/{ticket_id}")
        self.assertEqual(details.json()["operator_notes"][0]["body"], "Internal review note.")

        events = await self.client.get(f"/tickets/{ticket_id}/events")
        self.assertEqual(events.status_code, 200, events.text)
        self.assertTrue(any(event["action"] == "operator.mark_reviewed" for event in events.json()))

    async def test_full_complaint_to_review_and_status_workflow(self) -> None:
        excerpt = "Бан за читерство рассматривается по процедуре обжалования."
        with self.repository._connection() as connection:
            connection.execute(
                """INSERT INTO rules
                   (document_name, rule_id, rule_title, rule_text, source_url, language, version_or_date)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    "QA fixture rules",
                    "QA-1",
                    "Ban appeal",
                    excerpt,
                    "https://rules.example.test/fixture",
                    "ru",
                    "QA fixture version 1",
                ),
            )
        created = await self.client.post(
            "/tickets",
            data={
                "player_id": "workflow-player",
                "message": "Прошу обжаловать бан за читерство.",
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        ticket_id = created.json()["ticket_id"]

        with patch.dict("os.environ", {"LLM_API_KEY": "", "LLM_MODEL": ""}):
            analysis = await self.client.post(
                f"/tickets/{ticket_id}/analyze-structured"
            )
            self.assertEqual(analysis.status_code, 200, analysis.text)
            self.assertEqual(analysis.json()["rule_references"][0]["exact_excerpt"], excerpt)

            generated = await self.client.post(
                f"/tickets/{ticket_id}/generate-reply", json={}
            )
            self.assertEqual(generated.status_code, 201, generated.text)
            self.assertIn("черновик", generated.json()["body"].casefold())
            self.assertIn("QA-1", generated.json()["body"])

        reviewed = await self.client.post(
            f"/tickets/{ticket_id}/decisions",
            json={"decision": "mark_reviewed", "draft_id": generated.json()["id"]},
        )
        self.assertEqual(reviewed.status_code, 201, reviewed.text)
        updated = await self.client.patch(
            f"/tickets/{ticket_id}/status", json={"status": "Processing"}
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        detail = await self.client.get(f"/tickets/{ticket_id}")
        self.assertEqual(detail.json()["draft_status"], "reviewed")
        self.assertEqual(detail.json()["status"], "Processing")

    async def test_attachment_is_persisted_and_downloadable(self) -> None:
        ticket = await self.create_ticket(
            files=[("attachments", ("proof.txt", b"evidence", "text/plain"))]
        )
        attachment = ticket["attachments"][0]
        response = await self.client.get(
            f"/tickets/{ticket['ticket_id']}/attachments/{attachment['attachment_id']}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"evidence")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")

    async def test_attachment_upload_enforces_type_and_size_limits(self) -> None:
        unsupported = await self.client.post(
            "/tickets",
            data={"player_id": "player-1", "message": "File test"},
            files=[("attachments", ("script.svg", b"<svg></svg>", "image/svg+xml"))],
        )
        mismatched = await self.client.post(
            "/tickets",
            data={"player_id": "player-1", "message": "File test"},
            files=[("attachments", ("fake.png", b"not a PNG", "image/png"))],
        )
        oversized = await self.client.post(
            "/tickets",
            data={"player_id": "player-1", "message": "File test"},
            files=[
                (
                    "attachments",
                    ("large.txt", b"x" * (10 * 1024 * 1024 + 1), "text/plain"),
                )
            ],
        )

        self.assertEqual(unsupported.status_code, 415)
        self.assertEqual(unsupported.json()["error"]["code"], "unsupported_file_type")
        self.assertEqual(mismatched.status_code, 415)
        self.assertEqual(mismatched.json()["error"]["code"], "invalid_file_content")
        self.assertEqual(oversized.status_code, 413)
        self.assertEqual(oversized.json()["error"]["code"], "attachment_too_large")
        self.assertEqual((await self.client.get("/tickets")).json(), [])

    async def test_validation_errors_use_api_error_shape(self) -> None:
        response = await self.client.post(
            "/tickets",
            data={"player_id": "", "message": ""},
        )
        ticket = await self.create_ticket()
        malformed_json = await self.client.post(
            f"/tickets/{ticket['ticket_id']}/analysis",
            content="{",
            headers={"Content-Type": "application/json"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "validation_error")
        self.assertEqual(malformed_json.status_code, 422)
        self.assertEqual(malformed_json.json()["error"]["code"], "validation_error")

    async def test_local_frontend_cors_preflight_is_allowed(self) -> None:
        response = await self.client.options(
            "/tickets",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:5173")

    async def test_analysis_is_saved_and_unknown_rules_are_rejected(self) -> None:
        ticket = await self.create_ticket()
        ticket_id = ticket["ticket_id"]
        analysis = {
            "category": "Gameplay",
            "priority": "High",
            "extracted_facts": ["The report includes a screenshot"],
            "matched_rules": [],
            "draft_reply": "Thank you. An operator will review your report.",
            "confidence": 0.8,
            "escalation_required": False,
            "escalation_reason": None,
        }

        saved = await self.client.post(f"/tickets/{ticket_id}/analysis", json=analysis)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["category"], "Gameplay")
        self.assertEqual(saved.json()["extracted_facts"], analysis["extracted_facts"])
        self.assertEqual(saved.json()["status"], "New")

        analysis["matched_rules"] = [
            {"document_name": "unverified", "rule_id": "not-loaded"}
        ]
        rejected = await self.client.post(
            f"/tickets/{ticket_id}/analysis", json=analysis
        )
        self.assertEqual(rejected.status_code, 422)
        self.assertEqual(rejected.json()["error"]["code"], "unknown_rule")
        unchanged = await self.client.get(f"/tickets/{ticket_id}")
        self.assertEqual(unchanged.json()["category"], "Gameplay")
        self.assertEqual(unchanged.json()["matched_rules"], [])

    async def test_analysis_failure_does_not_remove_ticket(self) -> None:
        ticket = await self.create_ticket()
        ticket_id = ticket["ticket_id"]
        response = await self.client.post(
            f"/tickets/{ticket_id}/analysis",
            json={
                "category": "Gameplay",
                "priority": "Normal",
                "extracted_facts": [],
                "matched_rules": [],
                "draft_reply": "Draft",
                "confidence": 1.2,
                "escalation_required": False,
                "escalation_reason": None,
            },
        )

        self.assertEqual(response.status_code, 422)
        saved_ticket = await self.client.get(f"/tickets/{ticket_id}")
        self.assertEqual(saved_ticket.status_code, 200)

    async def test_missing_ticket_returns_404(self) -> None:
        response = await self.client.get("/tickets/missing")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "not_found")

    async def test_rules_catalog_starts_empty(self) -> None:
        response = await self.client.get("/rules")
        invalid_limit = await self.client.get("/rules?limit=0")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"items": [], "count": 0})
        self.assertEqual(invalid_limit.status_code, 422)


if __name__ == "__main__":
    unittest.main()
