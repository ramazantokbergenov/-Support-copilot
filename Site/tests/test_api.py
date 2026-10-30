import tempfile
import unittest
from pathlib import Path

import httpx

from app.database import TicketRepository
from app.main import create_app


class TicketApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        repository = TicketRepository(Path(self.temp_dir.name) / "test.db")
        transport = httpx.ASGITransport(app=create_app(repository))
        self.client = httpx.AsyncClient(transport=transport, base_url="http://test")

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self.temp_dir.cleanup()

    async def create_ticket(
        self, *, files: list[tuple[str, tuple]] | None = None
    ) -> dict:
        response = await self.client.post(
            "/tickets",
            data={"player_id": "player-1", "message": "Please review this report"},
            files=files,
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

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

    async def test_validation_errors_use_api_error_shape(self) -> None:
        response = await self.client.post(
            "/tickets",
            data={"player_id": "", "message": ""},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "validation_error")

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
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"items": [], "count": 0})


if __name__ == "__main__":
    unittest.main()
