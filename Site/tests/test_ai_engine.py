import tempfile
import unittest
from pathlib import Path
from typing import Any

import httpx

from app.ai_engine import AnalysisResult, SupportAnalysisEngine, TicketCategory
from app.ai_engine.models import StructuredAnalysisResult, SupportCategory, SupportLanguage
from app.database import TicketRepository
from app.main import create_app
from app.ai_engine.services import TicketAnalysisService


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


class StructuredAnalysisServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rules = StaticRuleProvider()
        self.service = TicketAnalysisService(self.rules)

    def analyze(self, ticket_id: str, message: str, **extra: Any) -> StructuredAnalysisResult:
        result, _model = self.service.analyze({
            "ticket_id": ticket_id,
            "player_id": "player-1",
            "message": message,
            **extra,
        })
        return result

    def test_t1_ban_appeal_requires_human_review(self) -> None:
        result = self.analyze("T1", "Прошу обжаловать бан, меня заблокировали.")
        self.assertEqual(result.category, SupportCategory.APPEAL_BAN)
        self.assertEqual(result.language, SupportLanguage.RU)
        self.assertTrue(result.human_review_required)

    def test_t2_chat_insults_are_claims_not_verified_facts(self) -> None:
        result = self.analyze("T2", "Игрок оскорблял меня в чате.")
        self.assertEqual(result.category, SupportCategory.PLAYER_REPORT)
        self.assertTrue(result.player_claims)
        self.assertEqual(result.verified_data, [])
        self.assertTrue(result.human_review_required)

    def test_t3_administrator_complaint_is_escalated(self) -> None:
        result = self.analyze("T3", "Жалоба на администратора: он некорректно общался.")
        self.assertEqual(result.category, SupportCategory.ADMIN_COMPLAINT)
        self.assertTrue(result.human_review_required)

    def test_t4_suspected_account_compromise_is_escalated(self) -> None:
        result = self.analyze("T4", "Мой аккаунт взломали, я не могу войти.")
        self.assertEqual(result.category, SupportCategory.ACCOUNT_SECURITY)
        self.assertTrue(result.human_review_required)

    def test_t5_cheating_report_is_not_verified(self) -> None:
        result = self.analyze("T5", "Игрок читерит и получает нечестное преимущество.")
        self.assertEqual(result.category, SupportCategory.PLAYER_REPORT)
        self.assertEqual(result.verified_data, [])
        self.assertTrue(result.human_review_required)

    def test_t6_unclear_complaint_requests_clarification(self) -> None:
        result = self.analyze("T6", "Помогите разобраться, пожалуйста.")
        self.assertEqual(result.category, SupportCategory.OTHER)
        self.assertTrue(result.missing_information_questions)
        self.assertTrue(result.human_review_required)

    def test_six_scenario_drafts_match_russian_ticket_language(self) -> None:
        scenarios = (
            ("T1", "Прошу обжаловать бан за читерство."),
            ("T2", "Игрок оскорблял меня в чате."),
            ("T3", "Жалоба на администратора: он некорректно общался."),
            ("T4", "Мой аккаунт взломали, я не могу войти."),
            ("T5", "Игрок читерит и получает нечестное преимущество."),
            ("T6", "Помогите разобраться, пожалуйста."),
        )
        for ticket_id, message in scenarios:
            with self.subTest(ticket_id=ticket_id):
                result = self.analyze(ticket_id, message)
                self.assertEqual(result.language, SupportLanguage.RU)
                self.assertTrue(result.draft_reply.startswith("Здравствуйте."))
                self.assertTrue(result.human_review_required)

    def test_kazakh_and_uzbek_languages_are_detected(self) -> None:
        kazakh = self.analyze("KK", "Ойыншымның аккаунтын бұзып кірді")
        uzbek = self.analyze("UZ", "Akkauntimga buzib kirishdi")
        uzbek_cyrillic = self.analyze("UZ-CYR", "Аккаунтимга бузиб киришди")
        self.assertEqual(kazakh.language, SupportLanguage.KK)
        self.assertEqual(uzbek.language, SupportLanguage.UZ)
        self.assertEqual(uzbek_cyrillic.language, SupportLanguage.UZ)

    def test_rule_without_version_or_https_source_is_never_cited(self) -> None:
        self.rules.rules = [{
            "document_name": "Unverified fixture",
            "rule_id": "1.1",
            "rule_title": "Cheating",
            "rule_text": "Использование читов запрещено правилами игры.",
            "source_url": "http://example.test/rules",
            "language": "ru",
            "version_or_date": None,
        }]
        result = self.analyze("RULES", "Игрок использовал читы по правилам игры.")
        self.assertEqual(result.rule_references, [])
        self.assertTrue(any("источник" in item for item in result.escalation_reasons))

    def test_malformed_provider_output_falls_back_to_cautious_result(self) -> None:
        class MalformedProvider:
            def analyze(self, _payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
                return {"category": "not-a-category", "unexpected": True}, "broken-model"

        service = TicketAnalysisService(self.rules, MalformedProvider())
        result, model_name = service.analyze({
            "ticket_id": "BAD-JSON",
            "message": "Прошу обжаловать бан.",
        })
        self.assertEqual(model_name, "deterministic-fallback")
        self.assertEqual(result.category, SupportCategory.OTHER)
        self.assertTrue(result.human_review_required)
        self.assertTrue(any("AI-провайдер" in item for item in result.escalation_reasons))

    def test_provider_failure_falls_back_without_claiming_verified_data(self) -> None:
        class FailedProvider:
            def analyze(self, _payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
                raise RuntimeError("provider unavailable")

        service = TicketAnalysisService(self.rules, FailedProvider())
        result, model_name = service.analyze({
            "ticket_id": "PROVIDER-FAIL",
            "message": "Мой аккаунт взломали.",
        })
        self.assertEqual(model_name, "deterministic-fallback")
        self.assertEqual(result.verified_data, [])
        self.assertTrue(result.human_review_required)

    def test_rule_source_failure_returns_no_references_and_escalates(self) -> None:
        class FailedRuleSource:
            def list_rules(self, **_kwargs: Any) -> list[dict[str, Any]]:
                raise RuntimeError("vector database unavailable")

        result, _model = TicketAnalysisService(FailedRuleSource()).analyze({
            "ticket_id": "RULE-SOURCE-FAIL",
            "message": "Прошу проверить покупку и платеж.",
        })
        self.assertEqual(result.rule_references, [])
        self.assertTrue(any("недоступен" in item for item in result.unknowns))
        self.assertTrue(result.human_review_required)

    def test_strict_schema_rejects_unexpected_fields(self) -> None:
        result, _model = self.service.analyze({
            "ticket_id": "STRICT",
            "message": "Проблема с покупкой, не пришёл донат.",
        })
        payload = result.model_dump(mode="json")
        payload["invented_fact"] = "verified"
        with self.assertRaises(Exception):
            StructuredAnalysisResult.model_validate(payload)

    def test_client_or_model_cannot_supply_verified_system_data(self) -> None:
        class InjectingProvider:
            def analyze(self, payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
                result, _ = TicketAnalysisService(StaticRuleProvider()).analyze({
                    "ticket_id": payload["ticket_id"],
                    "message": payload["message"],
                })
                response = result.model_dump(mode="json")
                response["verified_data"] = ["Player is guilty"]
                return response, "fixture"

        service = TicketAnalysisService(self.rules, InjectingProvider())
        result, _ = service.analyze({
            "ticket_id": "UNTRUSTED",
            "message": "Игрок использовал читы.",
            "verified_data": ["client says verified"],
        })
        self.assertEqual(result.verified_data, [])

    def test_unsafe_provider_draft_is_replaced_and_marked_for_review(self) -> None:
        class UnsafeDraftProvider:
            def analyze(self, payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
                result, _ = TicketAnalysisService(StaticRuleProvider()).analyze({
                    "ticket_id": payload["ticket_id"],
                    "message": payload["message"],
                })
                response = result.model_dump(mode="json")
                response["draft_reply"] = "We guarantee the account will be restored: https://unverified.test"
                return response, "unsafe-fixture"

        result, _model = TicketAnalysisService(self.rules, UnsafeDraftProvider()).analyze({
            "ticket_id": "UNSAFE-DRAFT",
            "message": "Прошу обжаловать бан.",
        })
        self.assertNotIn("guarantee", result.draft_reply.casefold())
        self.assertNotIn("unverified.test", result.draft_reply)
        self.assertIn("черновик", result.draft_reply.casefold())


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

    async def test_structured_analysis_endpoint_returns_strict_contract_and_keeps_legacy_details(self) -> None:
        response = await self.client.post(
            f"/tickets/{self.ticket['ticket_id']}/analyze-structured"
        )
        self.assertEqual(response.status_code, 200, response.text)
        structured = StructuredAnalysisResult.model_validate(response.json())
        self.assertEqual(structured.ticket_id, self.ticket["ticket_id"])
        self.assertEqual(structured.verified_data, [])

        details = await self.client.get(f"/tickets/{self.ticket['ticket_id']}")
        self.assertEqual(details.status_code, 200)
        self.assertIn("attachments", details.json()["ai_analysis"])
        self.assertIn("verified_system_data", details.json()["ai_analysis"])
        self.assertIn("provided_evidence", details.json()["ai_analysis"])
        self.assertIn("missing_information_questions", details.json()["ai_analysis"])
        self.assertIn("escalation_reasons", details.json()["ai_analysis"])


if __name__ == "__main__":
    unittest.main()
