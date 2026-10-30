import re
from collections.abc import Iterable
from typing import Any, Protocol

from app.ai_engine.models import (
    AnalysisResult,
    AttachmentEvidence,
    MatchedRule,
    TicketCategory,
)


class RuleProvider(Protocol):
    def list_rules(
        self, *, query: str | None, language: str | None, limit: int
    ) -> list[dict[str, Any]]: ...


CATEGORY_TERMS: dict[TicketCategory, tuple[str, ...]] = {
    TicketCategory.APPEAL_BAN: (
        "ban",
        "banned",
        "unban",
        "appeal",
        "suspend",
        "sanction",
        "блокиров",
        "бан",
        "разбан",
        "апелляц",
        "обжал",
        "наказан",
        "санкц",
    ),
    TicketCategory.PLAYER_REPORT: (
        "report player",
        "player report",
        "cheat",
        "cheating",
        "hacker",
        "insult",
        "harass",
        "игрок",
        "чит",
        "оскорб",
        "обзывал",
        "угрожал",
        "чат",
    ),
    TicketCategory.ADMIN_COMPLAINT: (
        "admin",
        "administrator",
        "moderator",
        "staff",
        "админ",
        "администратор",
        "модератор",
        "сотрудник поддержки",
    ),
    TicketCategory.ACCOUNT_SECURITY: (
        "hacked",
        "hacker accessed",
        "account stolen",
        "stole my account",
        "password stolen",
        "unauthorized login",
        "взлом",
        "взломали",
        "угнали аккаунт",
        "украли аккаунт",
        "пароль украли",
        "чужой вход",
    ),
    TicketCategory.PAYMENT_PURCHASE: (
        "payment",
        "purchase",
        "bought",
        "donation",
        "charge",
        "transaction",
        "платеж",
        "платёж",
        "покуп",
        "купил",
        "донат",
        "оплат",
        "транзакц",
    ),
    TicketCategory.BUG_TECHNICAL: (
        "bug",
        "crash",
        "error",
        "doesn't work",
        "does not work",
        "technical",
        "баг",
        "ошибк",
        "вылет",
        "не работает",
        "техническ",
        "завис",
    ),
}

STOP_WORDS = {
    "about",
    "after",
    "again",
    "also",
    "because",
    "been",
    "before",
    "being",
    "could",
    "from",
    "have",
    "into",
    "just",
    "more",
    "that",
    "their",
    "there",
    "they",
    "this",
    "with",
    "your",
    "всем",
    "всего",
    "если",
    "здесь",
    "когда",
    "который",
    "может",
    "мне",
    "меня",
    "моя",
    "мой",
    "нами",
    "очень",
    "после",
    "потом",
    "просто",
    "сейчас",
    "также",
    "этого",
    "этот",
    "я",
}

THREAT_TERMS = (
    "kill you",
    "i will kill",
    "death threat",
    "suicide",
    "self harm",
    "убью",
    "убить",
    "убийством",
    "угроза жизни",
    "суицид",
    "самоубийств",
    "причиню вред",
)

LOG_TERMS = (
    "game log",
    "server log",
    "check the logs",
    "transaction history",
    "payment history",
    "игровых лог",
    "проверк лог",
    "истори транзакц",
    "истори платеж",
)

CONTRADICTION_TERMS = (
    "contradict",
    "conflicting evidence",
    "does not match",
    "не совпадает",
    "противореч",
    "не сходится",
    "разные версии",
)


def detect_language(text: str) -> str:
    cyrillic = len(re.findall(r"[А-Яа-яЁё]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if cyrillic == 0 and latin == 0:
        return "unknown"
    return "ru" if cyrillic >= latin else "en"


def _contains_term(text: str, terms: Iterable[str]) -> bool:
    lowered = text.casefold()
    return any(term in lowered for term in terms)


def classify_ticket(message: str) -> tuple[TicketCategory, str, float]:
    lowered = message.casefold()
    scores = {
        category: sum(1 for term in terms if term in lowered)
        for category, terms in CATEGORY_TERMS.items()
    }
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_category, best_score = ranked[0]
    second_score = ranked[1][1]

    if best_score == 0:
        return (
            TicketCategory.OTHER_UNCLEAR,
            "В сообщении не найдено достаточно признаков для более точной категории.",
            0.3,
        )
    if best_score == second_score:
        return (
            TicketCategory.OTHER_UNCLEAR,
            "Ключевые слова подходят нескольким категориям; нужна ручная проверка.",
            0.4,
        )

    confidence = min(0.82, 0.5 + 0.1 * (best_score - second_score) + 0.04 * best_score)
    matched_terms = [term for term in CATEGORY_TERMS[best_category] if term in lowered]
    if detect_language(message) == "en":
        reason = "Category selected based on terms in the message: "
        reason += f"{', '.join(matched_terms[:3])}."
    else:
        reason = "Категория выбрана по словам из сообщения: "
        reason += f"{', '.join(matched_terms[:3])}."
    return best_category, reason, confidence


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zа-яё0-9]+", text.casefold())
        if len(token) >= 3 and token not in STOP_WORDS
    }


def retrieve_rules(
    message: str,
    rules: Iterable[dict[str, Any]],
    *,
    language: str,
    limit: int = 3,
) -> list[MatchedRule]:
    query_tokens = _tokens(message)
    if not query_tokens:
        return []

    ranked: list[tuple[int, dict[str, Any]]] = []
    for rule in rules:
        rule_language = str(rule.get("language", "")).casefold()
        if language != "unknown" and rule_language not in {
            language,
            "unknown",
            "mixed",
        }:
            continue
        searchable = " ".join(
            str(rule.get(field, ""))
            for field in ("rule_title", "rule_id", "rule_text")
        )
        overlap = query_tokens.intersection(_tokens(searchable))
        if len(overlap) >= 2:
            ranked.append((len(overlap), rule))

    ranked.sort(
        key=lambda item: (
            -item[0],
            str(item[1].get("document_name", "")),
            str(item[1].get("rule_id", "")),
        )
    )
    results: list[MatchedRule] = []
    for _, rule in ranked[:limit]:
        results.append(
            MatchedRule(
                document_name=rule["document_name"],
                rule_id=rule["rule_id"],
                rule_title=rule["rule_title"],
                excerpt=rule["rule_text"],
                source_url=rule["source_url"],
                language=rule["language"],
                version_or_date=rule.get("version_or_date"),
            )
        )
    return results


def _claims(message: str) -> list[str]:
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", message.strip())
        if sentence.strip()
    ]
    return sentences or ([message.strip()] if message.strip() else [])


def _unknowns(
    category: TicketCategory, attachments: list[dict[str, Any]], message: str
) -> list[str]:
    unknowns: list[str] = []
    if attachments:
        unknowns.append(
            "Содержимое вложений не анализировалось; оператору нужно проверить файлы."
        )
    else:
        unknowns.append("Вложения или другие подтверждающие материалы не предоставлены.")

    if category in {
        TicketCategory.APPEAL_BAN,
        TicketCategory.ADMIN_COMPLAINT,
        TicketCategory.PLAYER_REPORT,
    } and not _contains_term(message, ("время", "дата", "час", "time", "date")):
        unknowns.append("Не указаны точные дата и время описанного события.")

    if _contains_term(message, LOG_TERMS):
        unknowns.append(
            "Внутренние игровые логи и системные данные недоступны этому модулю."
        )
    return unknowns


def _draft_reply(language: str, rules: list[MatchedRule]) -> str:
    if language == "ru":
        if rules:
            citations = "; ".join(
                f'{rule.document_name}, пункт {rule.rule_id} ({rule.source_url})'
                for rule in rules
            )
            return (
                "Спасибо за обращение. Оператор проверит предоставленную информацию "
                f"и применимость указанных материалов: {citations}. Этот ответ "
                "является черновиком; решение принимает оператор."
            )
        return (
            "Спасибо за обращение. Подходящий пункт в доступной базе правил не найден. "
            "Оператор проверит обращение и при необходимости уточнит информацию. "
            "Этот ответ является черновиком; решение принимает оператор."
        )

    if language == "en":
        if rules:
            citations = "; ".join(
                f'{rule.document_name}, section {rule.rule_id} ({rule.source_url})'
                for rule in rules
            )
            return (
                "Thank you for contacting support. An operator will review the "
                f"information and the applicability of these materials: {citations}. "
                "This is a draft; the operator makes the final decision."
            )
        return (
            "Thank you for contacting support. No matching section was found in the "
            "available rules database. An operator will review the report and may "
            "request more information. This is a draft; the operator makes the final "
            "decision."
        )

    return (
        "Обращение получено. / Your report has been received. "
        "Оператор проверит информацию. / An operator will review the information."
    )


class SupportAnalysisEngine:
    def __init__(self, rule_provider: RuleProvider) -> None:
        self.rule_provider = rule_provider

    def analyze(self, ticket: dict[str, Any]) -> AnalysisResult:
        message = str(ticket.get("message", "")).strip()
        if not message:
            raise ValueError("Ticket message must not be empty")

        attachments = list(ticket.get("attachments") or [])
        language = detect_language(message)
        category, category_reason, confidence = classify_ticket(message)
        rules = self.rule_provider.list_rules(
            query=None, language=None, limit=10000
        )
        matched_rules = retrieve_rules(message, rules, language=language)

        escalation_reasons: list[str] = []
        if category in {
            TicketCategory.APPEAL_BAN,
            TicketCategory.ADMIN_COMPLAINT,
            TicketCategory.ACCOUNT_SECURITY,
        }:
            escalation_reasons.append(
                f"Категория «{category.value}» требует решения оператора."
            )
        if _contains_term(message, THREAT_TERMS):
            escalation_reasons.append(
                "Обнаружены признаки серьёзной угрозы или опасной ситуации."
            )
        if _contains_term(message, LOG_TERMS):
            escalation_reasons.append(
                "Для проверки могут потребоваться недоступные модулю системные логи."
            )
        if _contains_term(message, CONTRADICTION_TERMS):
            escalation_reasons.append(
                "В обращении указаны возможные противоречия; требуется ручная проверка."
            )
        if category == TicketCategory.PLAYER_REPORT:
            if attachments:
                escalation_reasons.append(
                    "Содержимое вложений не анализировалось; достаточность доказательств "
                    "должен оценить оператор."
                )
            else:
                escalation_reasons.append(
                    "Жалоба на игрока не содержит вложений для подтверждения утверждений."
                )
        if not matched_rules:
            escalation_reasons.append(
                "Подходящий пункт не найден в доступной базе проверенных правил."
            )
        if confidence < 0.5:
            escalation_reasons.append(
                "Уверенность классификации низкая; автоматическое решение невозможно."
            )

        return AnalysisResult(
            category=category,
            category_reason=category_reason,
            language=language,
            summary=_claims(message)[0][:500],
            player_claims=_claims(message),
            attachments=[
                AttachmentEvidence(
                    attachment_id=str(item.get("attachment_id", "")),
                    filename=str(item.get("filename", "attachment")),
                    content_type=str(
                        item.get("content_type", "application/octet-stream")
                    ),
                    size_bytes=max(0, int(item.get("size_bytes", 0))),
                    inspected=False,
                )
                for item in attachments
            ],
            verified_system_data=[],
            unknowns=_unknowns(category, attachments, message),
            matched_rules=matched_rules,
            draft_reply=_draft_reply(language, matched_rules),
            confidence=confidence,
            escalation_required=bool(escalation_reasons),
            escalation_reason=" ".join(escalation_reasons),
        )
