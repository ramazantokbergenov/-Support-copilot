import tempfile
import unittest
from pathlib import Path
from typing import Any

import httpx

from app.ai_engine import AnalysisResult, SupportAnalysisEngine, TicketCategory
from app.database import TicketRepository
from app.main import create_app


class StaticRuleProvider:
    def __init__(self, rules: list[dict[str, Any]] | None = None) -> None:
        self.rules = rules or []

    def list_rules(
        self, *, query: str | None, language: str | None, limit: int
    ) -> list[dict[str, Any]]:
        _ = (query, language)
        return self.rules[:limit]


class AiClassificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = SupportAnalysisEngine(StaticRuleProvider())

    def analyze(self, message: str, attachments: list[dict] | None = None) -> AnalysisResult:
        return self.engine.analyze(
            {
                "message": message,
                "attachments": attachments or [],
            }
        )

    def test_ban_appeal_is_classified_and_escalated(self) -> None:
        result = self.analyze("Прошу обжаловать бан за читерство, я не использовал читы.")
        self.assertEqual(result.category, TicketCategory.APPEAL_BAN)
        self.assertTrue(result.escalation_required)
        self.assertTrue(result.player_claims)
        self.assertEqual(result.verified_system_data, [])

    def test_chat_insult_is_player_report(self) -> None:
        result = self.analyze("Игрок оскорблял меня в чате.")
        self.assertEqual(result.category, TicketCategory.PLAYER_REPORT)
        self.assertTrue(result.escalation_required)

    def test_admin_complaint_is_escalated(self) -> None:
        result = self.analyze("Жалоба на администратора: он некорректно общался.")
        self.assertEqual(result.category, TicketCategory.ADMIN_COMPLAINT)
        self.assertTrue(result.escalation_required)

    def test_possible_account_hack_is_escalated(self) -> None:
        result = self.analyze("Мой аккаунт взломали, я не могу войти.")
        self.assertEqual(result.category, TicketCategory.ACCOUNT_SECURITY)
        self.assertTrue(result.escalation_required)

    def test_cheating_claim_without_evidence_is_not_verified(self) -> None:
        result = self.analyze("Игрок читерит и получает нечестное преимущество.")
        self.assertEqual(result.category, TicketCategory.PLAYER_REPORT)
        self.assertTrue(result.escalation_required)
        self.assertEqual(result.verified_system_data, [])
        self.assertTrue(
            any("не содерж" in reason for reason in result.escalation_reason.split("."))
        )

    def test_unclear_message_has_low_confidence_and_escalates(self) -> None:
        result = self.analyze("Помогите разобраться, пожалуйста.")
        self.assertEqual(result.category, TicketCategory.OTHER_UNCLEAR)
        self.assertLess(result.confidence, 0.5)
        self.assertTrue(result.escalation_required)

    def test_rule_retrieval_returns_exact_source_and_text(self) -> None:
        verified_rule = {
            "document_name": "Test fixture rules",
            "rule_id": "TEST-1",
            "rule_title": "Third-party programs",
            "rule_text": "Использование сторонних программ для преимущества запрещено.",
            "source_url": "https://example.test/rules",
            "language": "ru",
            "version_or_date": "test fixture",
        }
        engine = SupportAnalysisEngine(StaticRuleProvider([verified_rule]))
        result = engine.analyze(
            {"message": "Игрок использовал сторонние программы для преимущества."}
        )
        self.assertEqual(len(result.matched_rules), 1)
        self.assertEqual(result.matched_rules[0].rule_id, "TEST-1")
        self.assertEqual(result.matched_rules[0].excerpt, verified_rule["rule_text"])
        self.assertEqual(
            str(result.matched_rules[0].source_url), verified_rule["source_url"]
        )
        self.assertTrue(result.escalation_required)

    def test_attachment_metadata_is_not_claimed_as_inspected_evidence(self) -> None:
        result = self.analyze(
            "Игрок оскорблял меня в чате.",
            [
                {
                    "attachment_id": "fixture",
                    "filename": "proof.png",
                    "content_type": "image/png",
                    "size_bytes": 100,
                }
            ],
        )
        self.assertEqual(result.attachments[0].filename, "proof.png")
        self.assertFalse(result.attachments[0].inspected)
        self.assertEqual(result.verified_system_data, [])
        self.assertTrue(result.escalation_required)


class AiApiIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repository = TicketRepository(Path(self.temp_dir.name) / "test.db")
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(self.repository)),
            base_url="http://test",
        )
        created = await self.client.post(
            "/tickets",
            data={
                "player_id": "player-1",
                "message": "Меня забанили, прошу проверить апелляцию.",
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        self.ticket = created.json()

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self.temp_dir.cleanup()

    async def test_analysis_is_schema_validated_and_saved_for_backend(self) -> None:
        response = await self.client.post(
            f"/tickets/{self.ticket['ticket_id']}/analyze"
        )
        self.assertEqual(response.status_code, 200, response.text)

        result = AnalysisResult.model_validate(response.json())
        self.assertEqual(result.category, TicketCategory.APPEAL_BAN)
        self.assertTrue(result.escalation_required)
        self.assertEqual(result.matched_rules, [])

        stored = await self.client.get(f"/tickets/{self.ticket['ticket_id']}")
        self.assertEqual(stored.status_code, 200)
        self.assertEqual(stored.json()["category"], TicketCategory.APPEAL_BAN.value)
        self.assertTrue(stored.json()["escalation_required"])
        self.assertTrue(
            any(
                fact.startswith("PLAYER_CLAIMS:")
                for fact in stored.json()["extracted_facts"]
            )
        )
        self.assertEqual(
            stored.json()["ai_analysis"]["category"], result.category.value
        )
        self.assertEqual(stored.json()["ai_analysis"]["verified_system_data"], [])
        self.assertEqual(stored.json()["status"], "New")

    async def test_analysis_missing_ticket_returns_404(self) -> None:
        response = await self.client.post("/tickets/missing/analyze")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
