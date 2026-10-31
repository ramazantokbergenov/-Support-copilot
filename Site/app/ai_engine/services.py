import json
import logging
import re
from collections.abc import Iterable
from typing import Any, Protocol
from urllib.parse import urlparse

from app.ai_engine.models import (
    OfficialRuleReference,
    ProvidedEvidence,
    StructuredAnalysisResult,
    SupportCategory,
    SupportLanguage,
    SupportPriority,
)
from app.ai_engine.providers import AnalysisProvider


logger = logging.getLogger(__name__)
CONFIDENCE_THRESHOLD = 0.6


class RuleSource(Protocol):
    def list_rules(
        self, *, query: str | None, language: str | None, limit: int
    ) -> list[dict[str, Any]]: ...


class LanguageDetectionService:
    _KAZAKH_LETTERS = set("әғқңөұүһі")
    _UZBEK_MARKERS = (
        "shikoyat", "apellyats", "akkaunt", "to'lov", "tolov", "haqorat",
        "o'yinchi", "oyinchi", "ishlamay", "buzib kir", "ma'mur", "ҳақорат",
        "ўйинчи", "шикоят", "тўлов", "маъмур", "ўғир", "ишламай", "бузиб кир",
    )

    def detect(self, text: str) -> SupportLanguage:
        lowered = text.casefold()
        if any(letter in lowered for letter in self._KAZAKH_LETTERS):
            return SupportLanguage.KK
        if any(marker in lowered for marker in self._UZBEK_MARKERS):
            return SupportLanguage.UZ
        if re.search(r"[А-Яа-яЁё]", text):
            return SupportLanguage.RU
        if re.search(r"[A-Za-z]", text):
            return SupportLanguage.OTHER
        return SupportLanguage.OTHER


class TicketClassificationService:
    _TERMS: dict[SupportCategory, tuple[str, ...]] = {
        SupportCategory.APPEAL_BAN: (
            "ban", "banned", "unban", "appeal", "санкц", "бан", "разбан", "апелляц", "обжал", "блокиров",
            "блоктан", "блоктал", "апелляция", "апелляц", "bloklandi", "blok", "apellyats",
        ),
        SupportCategory.PLAYER_REPORT: (
            "report player", "player report", "cheat", "cheating", "insult", "harass", "чит", "оскорб", "обзывал", "жалоба на игрок",
            "қорлады", "балағат", "ойыншыны", "шағым", "haqorat", "shikoyat", "firib", "o'yinchi",
            "ҳақорат", "ўйинчи", "шикоят",
        ),
        SupportCategory.ADMIN_COMPLAINT: (
            "administrator", "moderator", "admin", "админ", "модератор", "сотрудник поддержки",
            "әкімш", "администратор", "ma'mur", "administrator", "маъмур",
        ),
        SupportCategory.ACCOUNT_SECURITY: (
            "hacked", "account stolen", "stole my account", "password stolen", "unauthorized login", "взлом", "угнали аккаунт", "украли аккаунт", "пароль украли",
            "аккаунтымды бұз", "ұрлап кетті", "buzib kir", "akkaunt o'g'ir", "parolimni", "аккаунт ўғир", "бузиб кир",
        ),
        SupportCategory.PAYMENT: (
            "payment", "purchase", "bought", "donation", "charge", "transaction", "платеж", "платёж", "покуп", "донат", "оплат", "транзакц",
            "төлем", "ақша", "to'lov", "tolov", "sotib", "donat", "тўлов", "пул",
        ),
        SupportCategory.BUG: (
            "bug", "crash", "error", "doesn't work", "does not work", "technical", "баг", "ошибк", "вылет", "не работает", "техническ", "завис",
            "қате", "істемей", "жұмыс істем", "xato", "ishlamay", "хато", "ишламай",
        ),
    }

    def classify(self, message: str) -> tuple[SupportCategory, float]:
        lowered = message.casefold()
        scores = {
            category: sum(term in lowered for term in terms)
            for category, terms in self._TERMS.items()
        }
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        best_category, best_score = ranked[0]
        second_score = ranked[1][1]
        if best_score == 0 or best_score == second_score:
            return SupportCategory.OTHER, 0.35 if best_score == 0 else 0.45
        confidence = min(0.82, 0.56 + 0.1 * (best_score - second_score) + 0.04 * best_score)
        if confidence < CONFIDENCE_THRESHOLD:
            return SupportCategory.OTHER, confidence
        return best_category, confidence


class FactExtractionService:
    def extract(
        self,
        message: str,
        attachments: Iterable[dict[str, Any]],
        trusted_system_data: Iterable[str] = (),
    ) -> tuple[list[str], list[ProvidedEvidence], list[str]]:
        claims = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", message) if part.strip()]
        evidence = [
            ProvidedEvidence(
                attachment_id=str(item.get("attachment_id", item.get("id", ""))),
                filename=str(item.get("filename", "attachment"))[:255],
                content_type=str(item.get("content_type", "application/octet-stream"))[:128],
                size_bytes=max(0, int(item.get("size_bytes", 0))),
            )
            for item in attachments
        ]
        unknowns = []
        if evidence:
            unknowns.append("Вложения получены, но их содержимое этим анализом не проверялось.")
        else:
            unknowns.append("Подтверждающие материалы не приложены.")
        verified = [str(value).strip() for value in trusted_system_data if str(value).strip()]
        return claims or [message.strip()], evidence, [*unknowns, *([] if verified else ["Данные игровых систем не подключены."])]


class MissingInformationService:
    _QUESTIONS: dict[SupportCategory, tuple[str, ...]] = {
        SupportCategory.APPEAL_BAN: (
            "Укажите дату и примерное время блокировки, а также причину, указанную в уведомлении.",
        ),
        SupportCategory.PLAYER_REPORT: (
            "Укажите ID игрока, сервер, дату и примерное время события.",
            "Если есть материалы, приложите исходный скриншот или видео без редактирования.",
        ),
        SupportCategory.ADMIN_COMPLAINT: (
            "Укажите имя или ID администратора, сервер, дату и примерное время общения.",
        ),
        SupportCategory.ACCOUNT_SECURITY: (
            "Укажите ID аккаунта и когда вы впервые заметили проблему. Не отправляйте пароль или коды доступа.",
        ),
        SupportCategory.PAYMENT: (
            "Укажите дату, сумму и идентификатор заказа или транзакции; не присылайте данные банковской карты.",
        ),
        SupportCategory.BUG: (
            "Опишите шаги, после которых возникает проблема, и укажите устройство, сервер и примерное время.",
        ),
        SupportCategory.OTHER: (
            "Уточните, что именно произошло, когда это случилось и какого результата вы ожидаете от поддержки.",
        ),
    }

    def detect(self, category: SupportCategory, message: str) -> list[str]:
        lowered = message.casefold()
        if category in {SupportCategory.APPEAL_BAN, SupportCategory.PLAYER_REPORT, SupportCategory.ADMIN_COMPLAINT}:
            if any(term in lowered for term in ("вчера", "сегодня", "час", "минут", "date", "time", "at ", "кеше", "бүгін", "vaqt", "sana")):
                return []
        if category == SupportCategory.PAYMENT and any(term in lowered for term in ("транзакц", "заказ", "order", "chek", "чек")):
            return []
        return list(self._QUESTIONS[category])


class OfficialRuleRetrievalService:
    def __init__(self, source: RuleSource, *, min_overlap: int = 2) -> None:
        self.source = source
        self.min_overlap = min_overlap

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {token for token in re.findall(r"[a-zа-яёәғқңөұүһі0-9]+", text.casefold()) if len(token) >= 3}

    def retrieve(self, message: str, language: SupportLanguage, limit: int = 5) -> list[OfficialRuleReference]:
        rows = self.source.list_rules(query=None, language=None, limit=10_000)
        query_tokens = self._tokens(message)
        ranked: list[tuple[int, dict[str, Any]]] = []
        for row in rows:
            title = str(row.get("document_title", row.get("document_name", ""))).strip()
            number = str(row.get("rule_number", row.get("rule_id", ""))).strip()
            excerpt = str(row.get("exact_excerpt", row.get("rule_text", ""))).strip()
            source_url = str(row.get("source_url", "")).strip()
            version = str(row.get("source_version_date", row.get("version_or_date", "")) or "").strip()
            parsed_url = urlparse(source_url)
            if not (title and number and excerpt and version and parsed_url.scheme == "https" and parsed_url.netloc):
                continue
            row_language = str(row.get("language", "")).casefold()
            if language != SupportLanguage.OTHER and row_language and row_language not in {language.value, "mixed", "unknown"}:
                continue
            overlap = len(query_tokens.intersection(self._tokens(f"{number} {excerpt}")))
            if overlap >= self.min_overlap:
                ranked.append((overlap, {
                    "document_title": title,
                    "rule_number": number,
                    "exact_excerpt": excerpt,
                    "source_url": source_url,
                    "source_version_date": version,
                }))
        ranked.sort(key=lambda item: (-item[0], item[1]["document_title"], item[1]["rule_number"]))
        return [OfficialRuleReference.model_validate(item) for _, item in ranked[:limit]]


class EscalationDetectionService:
    _SENSITIVE_TERMS = (
        "kill", "threat", "dox", "discriminat", "fraud", "theft", "steal", "hack", "cheat", "abuse",
        "убью", "угроз", "докс", "персональн", "дискрим", "мошен", "вор", "взлом", "чит", "насили",
        "қорқыт", "алаяқ", "ұрлық", "бұзу", "tahdid", "firib", "o'g'ir", "buzib", "haqorat",
    )

    def detect(
        self,
        message: str,
        category: SupportCategory,
        confidence: float,
        questions: list[str],
        rules: list[OfficialRuleReference],
    ) -> list[str]:
        reasons: list[str] = []
        if category == SupportCategory.APPEAL_BAN:
            reasons.append("Апелляция на санкцию требует решения оператора.")
        if category in {SupportCategory.PLAYER_REPORT, SupportCategory.ADMIN_COMPLAINT, SupportCategory.ACCOUNT_SECURITY}:
            reasons.append("Обвинение требует проверки человеком и доверенных данных.")
        if category == SupportCategory.PLAYER_REPORT:
            reasons.append("Жалоба на игрока не содержит подтверждённых системных данных.")
        if any(term in message.casefold() for term in self._SENSITIVE_TERMS):
            reasons.append("В сообщении есть признаки чувствительной жалобы или обвинения.")
        if not rules:
            reasons.append("Не найдено достаточно источников проверенных правил.")
        if questions:
            reasons.append("Для проверки не хватает существенной информации.")
        if confidence < CONFIDENCE_THRESHOLD:
            reasons.append("Уверенность классификации ниже проверенного порога.")
        if any(term in message.casefold() for term in ("винов", "наказать", "компенсац", "верните предмет", "restore my", "guilty", "compensation")):
            reasons.append("Итоговое решение о вине, санкции или компенсации принимает оператор.")
        return list(dict.fromkeys(reasons))


class DraftReplyGenerationService:
    _UNSUPPORTED_PROMISES = (
        "гарантируем", "обязательно верн", "точно верн", "компенсац будет", "разблокируем", "виновен",
        "we guarantee", "will definitely restore", "will compensate", "will unban", "is guilty",
        "кепілдік береміз", "міндетті түрде қайтарамыз", "albatta qaytaramiz", "kafolat beramiz",
    )

    def generate(
        self,
        language: SupportLanguage,
        questions: list[str],
        rules: list[OfficialRuleReference],
        candidate: str | None = None,
    ) -> str:
        if candidate and self._is_safe(candidate, rules):
            draft = candidate.strip()
            markers = {
                SupportLanguage.RU: ("черновик", "оператор"),
                SupportLanguage.KK: ("жоба", "оператор"),
                SupportLanguage.UZ: ("loyiha", "operator"),
                SupportLanguage.OTHER: ("draft", "operator"),
            }[language]
            if not all(marker in draft.casefold() for marker in markers):
                suffix = {
                    SupportLanguage.RU: "Это черновик для проверки оператором.",
                    SupportLanguage.KK: "Бұл оператор тексеретін жоба.",
                    SupportLanguage.UZ: "Bu operator ko'rib chiqishi uchun loyiha.",
                    SupportLanguage.OTHER: "This is a draft for operator review.",
                }[language]
                draft = f"{draft} {suffix}"
            return draft
        citation = ""
        if rules:
            first = rules[0]
            citation = f" Проверенный источник: {first.document_title}, пункт {first.rule_number} ({first.source_url})."
        question_text = f" {questions[0]}" if questions else ""
        if language == SupportLanguage.RU:
            return f"Здравствуйте. Спасибо за обращение. Оператор проверит описанную ситуацию.{question_text}{citation} Это черновик для проверки оператором; решение не принято."
        if language == SupportLanguage.KK:
            return f"Сәлеметсіз бе. Өтінішіңізге рақмет. Оператор сипатталған жағдайды тексереді.{question_text}{citation} Бұл оператор тексеретін жоба, шешім әлі қабылданған жоқ."
        if language == SupportLanguage.UZ:
            return f"Assalomu alaykum. Murojaatingiz uchun rahmat. Operator vaziyatni tekshiradi.{question_text}{citation} Bu operator ko'rib chiqishi uchun loyiha, yakuniy qaror emas."
        return f"Hello. Thank you for contacting support. An operator will review the situation.{question_text}{citation} This is a draft for operator review; no decision has been made."

    def _is_safe(self, candidate: str, rules: list[OfficialRuleReference]) -> bool:
        lowered = candidate.casefold()
        if any(term in lowered for term in self._UNSUPPORTED_PROMISES):
            return False
        allowed_urls = {str(rule.source_url).casefold() for rule in rules}
        cited_urls = {url.casefold() for url in re.findall(r"https?://[^\s)]+", candidate)}
        return cited_urls.issubset(allowed_urls)


class TicketAnalysisService:
    def __init__(
        self,
        rule_source: RuleSource,
        provider: AnalysisProvider | None = None,
        confidence_threshold: float = CONFIDENCE_THRESHOLD,
    ) -> None:
        self.language_detector = LanguageDetectionService()
        self.classifier = TicketClassificationService()
        self.fact_extractor = FactExtractionService()
        self.missing_information = MissingInformationService()
        self.rule_retrieval = OfficialRuleRetrievalService(rule_source)
        self.escalation = EscalationDetectionService()
        self.reply_generator = DraftReplyGenerationService()
        self.provider = provider
        self.confidence_threshold = confidence_threshold

    def analyze(
        self,
        ticket: dict[str, Any],
        *,
        trusted_system_data: Iterable[str] = (),
    ) -> tuple[StructuredAnalysisResult, str]:
        message = str(ticket.get("message", ticket.get("original_message", ""))).strip()
        if not message:
            raise ValueError("Ticket message must not be empty")
        ticket_id = str(ticket.get("ticket_id", ticket.get("id", "unknown")))
        language = self.language_detector.detect(message)
        category, baseline_confidence = self.classifier.classify(message)
        attachments = list(ticket.get("attachments") or [])
        claims, evidence, fact_unknowns = self.fact_extractor.extract(
            message, attachments, trusted_system_data
        )
        verified = [str(value).strip() for value in trusted_system_data if str(value).strip()]
        questions = self.missing_information.detect(category, message)
        retrieval_failed = False
        try:
            rules = self.rule_retrieval.retrieve(message, language)
        except Exception as exc:
            logger.warning("Official rule retrieval failed (%s)", type(exc).__name__)
            rules = []
            retrieval_failed = True
        priority = self._priority(ticket.get("priority"), message)
        confidence = baseline_confidence
        analysis_text = self._analysis_text(category, language, rules)
        candidate_reply = None
        provider_failure = False
        provider_requires_review = False
        provider_escalation_reasons: list[str] = []

        if self.provider is not None:
            try:
                raw, model_name = self.provider.analyze({
                    "ticket_id": ticket_id,
                    "language_hint": language.value,
                    "category_hint": category.value,
                    "player_id": ticket.get("player_id"),
                    "message": message,
                    "attachment_metadata": [item.model_dump(mode="json") for item in evidence],
                    "trusted_system_data": verified,
                    "official_rule_references": [item.model_dump(mode="json") for item in rules],
                    "required_schema": "StructuredAnalysisResult",
                })
                if isinstance(raw, str):
                    raw = json.loads(raw)
                proposed = StructuredAnalysisResult.model_validate(raw)
                if proposed.ticket_id != ticket_id:
                    raise ValueError("AI response ticket_id does not match request")
                category = proposed.category
                language = proposed.language
                confidence = proposed.confidence
                if confidence < self.confidence_threshold:
                    category = SupportCategory.OTHER
                analysis_text = proposed.analysis
                candidate_reply = proposed.draft_reply
                provider_requires_review = proposed.human_review_required
                provider_escalation_reasons = proposed.escalation_reasons
            except Exception as exc:
                logger.warning(
                    "AI provider failed (%s); using cautious analysis",
                    type(exc).__name__,
                )
                provider_failure = True
                model_name = "deterministic-fallback"
                confidence = min(confidence, 0.45)
                category = SupportCategory.OTHER if confidence < self.confidence_threshold else category
                analysis_text = "AI-провайдер недоступен или вернул некорректный результат; показана осторожная базовая оценка."
        else:
            model_name = "deterministic-baseline"

        escalation_reasons = self.escalation.detect(message, category, confidence, questions, rules)
        escalation_reasons.extend(provider_escalation_reasons)
        if provider_requires_review and not escalation_reasons:
            escalation_reasons.append("AI-провайдер рекомендует проверку оператором.")
        if provider_failure:
            escalation_reasons.append("Не удалось подтвердить анализ через AI-провайдер.")
        unknowns = list(dict.fromkeys([
            *fact_unknowns,
            *([] if verified else ["Нет доверенных игровых данных для подтверждения утверждений."]),
            *(["Поиск правил временно недоступен."] if retrieval_failed else []),
            *(["Подходящий актуальный официальный пункт не найден."] if not rules and not retrieval_failed else []),
        ]))
        draft = self.reply_generator.generate(language, questions, rules, candidate_reply)
        result = StructuredAnalysisResult(
            ticket_id=ticket_id,
            language=language,
            category=category,
            priority=priority,
            summary=(claims[0] if claims else message)[:500],
            player_claims=claims,
            provided_evidence=evidence,
            verified_data=verified,
            unknowns=unknowns,
            missing_information_questions=questions,
            rule_references=rules,
            analysis=analysis_text,
            draft_reply=draft,
            human_review_required=bool(escalation_reasons),
            escalation_reasons=escalation_reasons,
            confidence=max(0, min(1, confidence)),
        )
        return result, model_name

    def _analysis_text(
        self,
        category: SupportCategory,
        language: SupportLanguage,
        rules: list[OfficialRuleReference],
    ) -> str:
        if not rules:
            return "Классификация является предварительной. Проверенные официальные правила не найдены; требуется проверка оператором."
        return f"Предварительная категория: {category.value}. Найдено проверенных фрагментов правил: {len(rules)}. Требуется проверка оператором. Язык обращения: {language.value}."

    @staticmethod
    def _priority(value: Any, message: str) -> SupportPriority:
        normalized = str(value or "normal").casefold()
        if "urgent" in normalized or "сроч" in message.casefold():
            return SupportPriority.URGENT
        if normalized in {item.value for item in SupportPriority}:
            return SupportPriority(normalized)
        legacy = {"low": "low", "normal": "normal", "high": "high"}
        for key, priority in legacy.items():
            if key in normalized:
                return SupportPriority(priority)
        return SupportPriority.NORMAL