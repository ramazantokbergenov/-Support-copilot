import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator


DEFAULT_DATABASE_PATH = Path(
    os.environ.get("SUPPORT_COPILOT_DB", "support_copilot.db")
)


class TicketRepository:
    def __init__(self, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
        self.database_path = str(database_path)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        path = Path(self.database_path)
        if self.database_path != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tickets (
                    ticket_id TEXT PRIMARY KEY,
                    player_id TEXT NOT NULL,
                    message TEXT NOT NULL,
                    category TEXT,
                    priority TEXT NOT NULL,
                    status TEXT NOT NULL,
                    extracted_facts TEXT,
                    draft_reply TEXT,
                    confidence REAL,
                    escalation_required INTEGER,
                    escalation_reason TEXT,
                    ai_analysis_json TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS attachments (
                    attachment_id TEXT PRIMARY KEY,
                    ticket_id TEXT NOT NULL REFERENCES tickets(ticket_id) ON DELETE CASCADE,
                    filename TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    content BLOB NOT NULL
                );

                CREATE TABLE IF NOT EXISTS rules (
                    document_name TEXT NOT NULL,
                    rule_id TEXT NOT NULL,
                    rule_title TEXT NOT NULL,
                    rule_text TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    language TEXT NOT NULL,
                    version_or_date TEXT,
                    PRIMARY KEY (document_name, rule_id)
                );

                CREATE TABLE IF NOT EXISTS ticket_matched_rules (
                    ticket_id TEXT NOT NULL REFERENCES tickets(ticket_id) ON DELETE CASCADE,
                    document_name TEXT NOT NULL,
                    rule_id TEXT NOT NULL,
                    PRIMARY KEY (ticket_id, document_name, rule_id),
                    FOREIGN KEY (document_name, rule_id)
                        REFERENCES rules(document_name, rule_id)
                );

                CREATE INDEX IF NOT EXISTS idx_tickets_created_at
                    ON tickets(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_tickets_status
                    ON tickets(status);
                CREATE INDEX IF NOT EXISTS idx_rules_language
                    ON rules(language);
                """
            )
            ticket_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(tickets)").fetchall()
            }
            if "ai_analysis_json" not in ticket_columns:
                connection.execute(
                    "ALTER TABLE tickets ADD COLUMN ai_analysis_json TEXT"
                )

    def create_ticket(
        self,
        *,
        ticket_id: str,
        player_id: str,
        message: str,
        category: str | None,
        priority: str,
        created_at: str,
        attachments: list[dict[str, Any]],
    ) -> dict[str, Any]:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO tickets
                    (ticket_id, player_id, message, category, priority, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'New', ?)
                """,
                (ticket_id, player_id, message, category, priority, created_at),
            )
            connection.executemany(
                """
                INSERT INTO attachments
                    (attachment_id, ticket_id, filename, content_type, size_bytes, content)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item["attachment_id"],
                        ticket_id,
                        item["filename"],
                        item["content_type"],
                        item["size_bytes"],
                        item["content"],
                    )
                    for item in attachments
                ],
            )
        ticket = self.get_ticket(ticket_id)
        if ticket is None:
            raise RuntimeError("Created ticket could not be read from the database")
        return ticket

    def list_tickets(
        self,
        *,
        status: str | None,
        category: str | None,
        priority: str | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        parameters: list[Any] = []
        for column, value in (
            ("status", status),
            ("category", category),
            ("priority", priority),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                parameters.append(value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.extend((limit, offset))
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT ticket_id, player_id, category, priority, status, confidence,
                       escalation_required, created_at
                FROM tickets {where}
                ORDER BY created_at DESC, ticket_id
                LIMIT ? OFFSET ?
                """,
                parameters,
            ).fetchall()
        return [self._ticket_summary(row) for row in rows]

    def get_ticket(self, ticket_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)
            ).fetchone()
            if row is None:
                return None
            attachments = connection.execute(
                """
                SELECT attachment_id, filename, content_type, size_bytes
                FROM attachments WHERE ticket_id = ? ORDER BY rowid
                """,
                (ticket_id,),
            ).fetchall()
            rules = connection.execute(
                """
                SELECT r.document_name, r.rule_id, r.rule_title, r.rule_text,
                       r.source_url, r.language, r.version_or_date
                FROM rules r
                JOIN ticket_matched_rules m
                  ON m.document_name = r.document_name AND m.rule_id = r.rule_id
                WHERE m.ticket_id = ?
                ORDER BY r.document_name, r.rule_id
                """,
                (ticket_id,),
            ).fetchall()
        ticket = dict(row)
        ticket["extracted_facts"] = (
            json.loads(ticket["extracted_facts"])
            if ticket["extracted_facts"] is not None
            else None
        )
        ticket["ai_analysis"] = (
            json.loads(ticket["ai_analysis_json"])
            if ticket["ai_analysis_json"] is not None
            else None
        )
        ticket.pop("ai_analysis_json", None)
        ticket["escalation_required"] = (
            bool(ticket["escalation_required"])
            if ticket["escalation_required"] is not None
            else None
        )
        ticket["attachments"] = [dict(item) for item in attachments]
        ticket["matched_rules"] = [dict(item) for item in rules]
        return ticket

    def update_status(self, ticket_id: str, status: str) -> bool:
        with self._connection() as connection:
            cursor = connection.execute(
                "UPDATE tickets SET status = ? WHERE ticket_id = ?",
                (status, ticket_id),
            )
        return cursor.rowcount > 0

    def save_analysis(self, ticket_id: str, analysis: dict[str, Any]) -> bool:
        references = analysis["matched_rules"]
        with self._connection() as connection:
            ticket = connection.execute(
                "SELECT 1 FROM tickets WHERE ticket_id = ?", (ticket_id,)
            ).fetchone()
            if ticket is None:
                return False
            for reference in references:
                exists = connection.execute(
                    """
                    SELECT 1 FROM rules WHERE document_name = ? AND rule_id = ?
                    """,
                    (reference["document_name"], reference["rule_id"]),
                ).fetchone()
                if exists is None:
                    raise ValueError(
                        "Matched rule does not exist in the verified rules database: "
                        f'{reference["document_name"]}/{reference["rule_id"]}'
                    )
            connection.execute(
                """
                UPDATE tickets
                SET category = ?, priority = ?, extracted_facts = ?, draft_reply = ?,
                    confidence = ?, escalation_required = ?, escalation_reason = ?,
                    ai_analysis_json = ?
                WHERE ticket_id = ?
                """,
                (
                    analysis["category"],
                    analysis["priority"],
                    json.dumps(analysis["extracted_facts"], ensure_ascii=False),
                    analysis["draft_reply"],
                    analysis["confidence"],
                    int(analysis["escalation_required"]),
                    analysis["escalation_reason"],
                    (
                        json.dumps(
                            analysis["ai_analysis"],
                            ensure_ascii=False,
                        )
                        if analysis.get("ai_analysis") is not None
                        else None
                    ),
                    ticket_id,
                ),
            )
            connection.execute(
                "DELETE FROM ticket_matched_rules WHERE ticket_id = ?", (ticket_id,)
            )
            connection.executemany(
                """
                INSERT INTO ticket_matched_rules (ticket_id, document_name, rule_id)
                VALUES (?, ?, ?)
                """,
                [
                    (ticket_id, item["document_name"], item["rule_id"])
                    for item in references
                ],
            )
        return True

    def get_attachment(self, ticket_id: str, attachment_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT attachment_id, filename, content_type, size_bytes, content
                FROM attachments
                WHERE ticket_id = ? AND attachment_id = ?
                """,
                (ticket_id, attachment_id),
            ).fetchone()
        return dict(row) if row is not None else None

    def list_rules(
        self, *, query: str | None, language: str | None, limit: int
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        parameters: list[Any] = []
        if query:
            clauses.append(
                """
                (instr(lower(rule_title), lower(?)) > 0
                 OR instr(lower(rule_text), lower(?)) > 0
                 OR instr(lower(rule_id), lower(?)) > 0)
                """
            )
            parameters.extend((query, query, query))
        if language:
            clauses.append("language = ?")
            parameters.append(language)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(limit)
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT document_name, rule_id, rule_title, rule_text, source_url,
                       language, version_or_date
                FROM rules {where}
                ORDER BY document_name, rule_id
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _ticket_summary(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        if result["escalation_required"] is not None:
            result["escalation_required"] = bool(result["escalation_required"])
        return result
