import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
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

                CREATE TABLE IF NOT EXISTS ticket_reply_drafts (
                    draft_id TEXT PRIMARY KEY,
                    ticket_id TEXT NOT NULL REFERENCES tickets(ticket_id) ON DELETE CASCADE,
                    body TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending_review',
                    created_by TEXT NOT NULL,
                    updated_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(ticket_id, version)
                );

                CREATE TABLE IF NOT EXISTS operator_notes (
                    note_id TEXT PRIMARY KEY,
                    ticket_id TEXT NOT NULL REFERENCES tickets(ticket_id) ON DELETE CASCADE,
                    operator_id TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS audit_logs (
                    event_id TEXT PRIMARY KEY,
                    ticket_id TEXT NOT NULL REFERENCES tickets(ticket_id) ON DELETE CASCADE,
                    operator_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    old_value TEXT,
                    new_value TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_tickets_created_at
                    ON tickets(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_tickets_status
                    ON tickets(status);
                CREATE INDEX IF NOT EXISTS idx_rules_language
                    ON rules(language);
                CREATE INDEX IF NOT EXISTS idx_drafts_ticket_version
                    ON ticket_reply_drafts(ticket_id, version DESC);
                CREATE INDEX IF NOT EXISTS idx_notes_ticket_created
                    ON operator_notes(ticket_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_audit_ticket_created
                    ON audit_logs(ticket_id, created_at DESC);
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

    def health_check(self) -> None:
        with self._connection() as connection:
            connection.execute("SELECT 1").fetchone()

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
        query: str | None = None,
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
        if query and query.strip():
            clauses.append(
                "(instr(lower(ticket_id), lower(?)) > 0 "
                "OR instr(lower(player_id), lower(?)) > 0 "
                "OR instr(lower(message), lower(?)) > 0 "
                "OR instr(lower(coalesce(category, '')), lower(?)) > 0)"
            )
            search = query.strip()[:128]
            parameters.extend((search, search, search, search))
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
            draft = connection.execute(
                """SELECT draft_id, version, status FROM ticket_reply_drafts
                   WHERE ticket_id = ? ORDER BY version DESC LIMIT 1""",
                (ticket_id,),
            ).fetchone()
            notes = connection.execute(
                """SELECT note_id, operator_id, body, created_at FROM operator_notes
                   WHERE ticket_id = ? ORDER BY created_at DESC LIMIT 20""",
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
        ticket["draft_id"] = draft["draft_id"] if draft else None
        ticket["draft_version"] = draft["version"] if draft else None
        ticket["draft_status"] = draft["status"] if draft else None
        ticket["operator_notes"] = [
            {
                "id": note["note_id"],
                "operator_id": note["operator_id"],
                "body": note["body"],
                "created_at": note["created_at"],
            }
            for note in notes
        ]
        return ticket

    def update_status(self, ticket_id: str, status: str) -> bool:
        with self._connection() as connection:
            current = connection.execute(
                "SELECT status FROM tickets WHERE ticket_id = ?", (ticket_id,)
            ).fetchone()
            if current is None:
                return False
            cursor = connection.execute(
                "UPDATE tickets SET status = ? WHERE ticket_id = ?",
                (status, ticket_id),
            )
            if cursor.rowcount:
                self._insert_event(
                    connection,
                    ticket_id,
                    "local-operator",
                    "ticket.status_changed",
                    {"status": current["status"]},
                    {"status": status},
                    datetime.now(UTC).isoformat(),
                )
        return cursor.rowcount > 0

    def save_draft(
        self,
        ticket_id: str,
        body: str,
        *,
        draft_id: str | None,
        operator_id: str,
        now: str,
    ) -> dict[str, Any] | None:
        with self._connection() as connection:
            exists = connection.execute(
                "SELECT 1 FROM tickets WHERE ticket_id = ?", (ticket_id,)
            ).fetchone()
            if exists is None:
                return None
            old_body: str | None = None
            if draft_id:
                current = connection.execute(
                    """SELECT draft_id, body, version, created_at FROM ticket_reply_drafts
                       WHERE draft_id = ? AND ticket_id = ?""",
                    (draft_id, ticket_id),
                ).fetchone()
                if current is None:
                    return None
                old_body = current["body"]
                version = current["version"]
                created_at = current["created_at"]
                connection.execute(
                    """UPDATE ticket_reply_drafts
                       SET body = ?, status = 'pending_review', updated_by = ?, updated_at = ?
                       WHERE draft_id = ?""",
                    (body, operator_id, now, draft_id),
                )
                saved_id = draft_id
            else:
                latest = connection.execute(
                    "SELECT MAX(version) AS version FROM ticket_reply_drafts WHERE ticket_id = ?",
                    (ticket_id,),
                ).fetchone()
                version = int(latest["version"] or 0) + 1
                saved_id = str(uuid.uuid4())
                created_at = now
                connection.execute(
                    """INSERT INTO ticket_reply_drafts
                       (draft_id, ticket_id, body, version, status, created_by, updated_by, created_at, updated_at)
                       VALUES (?, ?, ?, ?, 'pending_review', ?, ?, ?, ?)""",
                    (saved_id, ticket_id, body, version, operator_id, operator_id, now, now),
                )
            connection.execute(
                "UPDATE tickets SET draft_reply = ? WHERE ticket_id = ?",
                (body, ticket_id),
            )
            self._insert_event(
                connection,
                ticket_id,
                operator_id,
                "reply.edited" if draft_id else "reply.saved",
                {"body": old_body} if old_body is not None else None,
                {"draft_id": saved_id, "body": body, "version": version},
                now,
            )
        return {
            "id": saved_id,
            "ticket_id": ticket_id,
            "body": body,
            "version": version,
            "status": "pending_review",
            "created_at": created_at,
        }

    def add_operator_note(
        self,
        ticket_id: str,
        body: str,
        *,
        operator_id: str,
        note_id: str,
        now: str,
    ) -> dict[str, Any] | None:
        with self._connection() as connection:
            exists = connection.execute(
                "SELECT 1 FROM tickets WHERE ticket_id = ?", (ticket_id,)
            ).fetchone()
            if exists is None:
                return None
            connection.execute(
                """INSERT INTO operator_notes (note_id, ticket_id, operator_id, body, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (note_id, ticket_id, operator_id, body, now),
            )
            self._insert_event(connection, ticket_id, operator_id, "operator.note_added", None, {"note_id": note_id}, now)
        return {"id": note_id, "ticket_id": ticket_id, "operator_id": operator_id, "body": body, "created_at": now}

    def record_decision(
        self,
        ticket_id: str,
        decision: str,
        *,
        draft_id: str | None,
        note: str | None,
        operator_id: str,
        now: str,
    ) -> dict[str, Any] | None:
        statuses = {
            "mark_reviewed": "reviewed",
            "unmark_reviewed": "pending_review",
            "approve": "approved",
            "reject": "rejected",
        }
        with self._connection() as connection:
            exists = connection.execute(
                "SELECT 1 FROM tickets WHERE ticket_id = ?", (ticket_id,)
            ).fetchone()
            if exists is None:
                return None
            if draft_id:
                draft = connection.execute(
                    "SELECT 1 FROM ticket_reply_drafts WHERE draft_id = ? AND ticket_id = ?",
                    (draft_id, ticket_id),
                ).fetchone()
                if draft is None:
                    return None
                if decision in statuses:
                    connection.execute(
                        """UPDATE ticket_reply_drafts SET status = ?, updated_by = ?, updated_at = ?
                           WHERE draft_id = ?""",
                        (statuses[decision], operator_id, now, draft_id),
                    )
            self._insert_event(
                connection,
                ticket_id,
                operator_id,
                f"operator.{decision}",
                None,
                {"draft_id": draft_id, "note": note},
                now,
            )
        return {"ticket_id": ticket_id, "decision": decision, "draft_id": draft_id, "created_at": now}

    def list_ticket_events(self, ticket_id: str, limit: int = 50) -> list[dict[str, Any]] | None:
        with self._connection() as connection:
            exists = connection.execute(
                "SELECT 1 FROM tickets WHERE ticket_id = ?", (ticket_id,)
            ).fetchone()
            if exists is None:
                return None
            rows = connection.execute(
                """SELECT event_id, operator_id, action, old_value, new_value, created_at
                   FROM audit_logs WHERE ticket_id = ? ORDER BY created_at DESC LIMIT ?""",
                (ticket_id, limit),
            ).fetchall()
        return [
            {
                "id": row["event_id"],
                "operator_id": row["operator_id"],
                "action": row["action"],
                "old_value": json.loads(row["old_value"]) if row["old_value"] else None,
                "new_value": json.loads(row["new_value"]) if row["new_value"] else None,
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    @staticmethod
    def _insert_event(
        connection: sqlite3.Connection,
        ticket_id: str,
        operator_id: str,
        action: str,
        old_value: Any,
        new_value: Any,
        created_at: str,
    ) -> None:
        connection.execute(
            """INSERT INTO audit_logs
               (event_id, ticket_id, operator_id, action, old_value, new_value, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()),
                ticket_id,
                operator_id,
                action,
                json.dumps(old_value, ensure_ascii=False) if old_value is not None else None,
                json.dumps(new_value, ensure_ascii=False) if new_value is not None else None,
                created_at,
            ),
        )

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
