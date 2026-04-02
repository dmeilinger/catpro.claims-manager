"""SQLite database for tracking processed claim emails."""

import sqlite3
from datetime import datetime, timezone

DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS processed_emails (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id          TEXT NOT NULL,
    internet_message_id TEXT NOT NULL,
    subject             TEXT,
    sender              TEXT,
    received_at         TEXT,
    processed_at        TEXT NOT NULL,
    claim_id            TEXT,
    status              TEXT NOT NULL DEFAULT 'pending',
    error_message       TEXT,
    UNIQUE(internet_message_id)
);
"""


class ClaimDatabase:
    def __init__(self, db_path: str = "claims.db"):
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(DB_SCHEMA)

    def is_duplicate(self, internet_message_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM processed_emails WHERE internet_message_id = ?",
            (internet_message_id,),
        ).fetchone()
        return row is not None

    def insert_pending(
        self,
        message_id: str,
        internet_message_id: str,
        subject: str,
        sender: str,
        received_at: str,
    ) -> int:
        cur = self._conn.execute(
            """INSERT INTO processed_emails
               (message_id, internet_message_id, subject, sender, received_at,
                processed_at, status)
               VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
            (
                message_id,
                internet_message_id,
                subject,
                sender,
                received_at,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def mark_success(self, row_id: int, claim_id: str) -> None:
        self._conn.execute(
            "UPDATE processed_emails SET status='success', claim_id=?, processed_at=? WHERE id=?",
            (claim_id, datetime.now(timezone.utc).isoformat(), row_id),
        )
        self._conn.commit()

    def mark_error(self, row_id: int, error_message: str) -> None:
        self._conn.execute(
            "UPDATE processed_emails SET status='error', error_message=?, processed_at=? WHERE id=?",
            (error_message, datetime.now(timezone.utc).isoformat(), row_id),
        )
        self._conn.commit()

    def get_history(self, limit: int = 50) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM processed_emails ORDER BY processed_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self._conn.close()
