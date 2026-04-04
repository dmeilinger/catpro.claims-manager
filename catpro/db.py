"""SQLite database for tracking processed claim emails."""

import json
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

CREATE TABLE IF NOT EXISTS claim_data (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id                INTEGER NOT NULL REFERENCES processed_emails(id),
    -- Extracted fields (from PDF/email parsing)
    insured_first_name      TEXT,
    insured_last_name       TEXT,
    insured_email           TEXT,
    insured_phone           TEXT,
    insured_cell            TEXT,
    insured_address1        TEXT,
    insured_city            TEXT,
    insured_state           TEXT,
    insured_zip             TEXT,
    policy_number           TEXT,
    secondary_insured_first TEXT,
    secondary_insured_last  TEXT,
    loss_date               TEXT,
    loss_type               TEXT,
    loss_description        TEXT,
    loss_address1           TEXT,
    loss_city               TEXT,
    loss_state              TEXT,
    loss_zip                TEXT,
    client_company_name     TEXT,
    client_claim_number     TEXT,
    agent_company           TEXT,
    agent_phone             TEXT,
    agent_email             TEXT,
    agent_address1          TEXT,
    agent_city              TEXT,
    agent_state             TEXT,
    agent_zip               TEXT,
    assigned_adjuster_name  TEXT,
    policy_effective        TEXT,
    policy_expiration       TEXT,
    -- Resolved FileTrac IDs (from claimAdd lookups)
    filetrac_company_id     TEXT,
    filetrac_contact_id     TEXT,
    filetrac_branch_id      TEXT,
    filetrac_adjuster_id    TEXT,
    filetrac_manager_id     TEXT,
    filetrac_csrf_token     TEXT,
    -- Full submission payload (JSON)
    submission_payload      TEXT,
    created_at              TEXT NOT NULL
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

    def insert_claim_data(
        self,
        email_id: int,
        claim_fields: dict,
        resolved_ids: dict | None = None,
        submission_payload: dict | None = None,
    ) -> int:
        resolved = resolved_ids or {}
        cur = self._conn.execute(
            """INSERT INTO claim_data (
                email_id,
                insured_first_name, insured_last_name, insured_email,
                insured_phone, insured_cell, insured_address1,
                insured_city, insured_state, insured_zip,
                policy_number, secondary_insured_first, secondary_insured_last,
                loss_date, loss_type, loss_description,
                loss_address1, loss_city, loss_state, loss_zip,
                client_company_name, client_claim_number,
                agent_company, agent_phone, agent_email,
                agent_address1, agent_city, agent_state, agent_zip,
                assigned_adjuster_name, policy_effective, policy_expiration,
                filetrac_company_id, filetrac_contact_id, filetrac_branch_id,
                filetrac_adjuster_id, filetrac_manager_id, filetrac_csrf_token,
                submission_payload, created_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )""",
            (
                email_id,
                claim_fields.get("insured_first_name"),
                claim_fields.get("insured_last_name"),
                claim_fields.get("insured_email"),
                claim_fields.get("insured_phone"),
                claim_fields.get("insured_cell"),
                claim_fields.get("insured_address1"),
                claim_fields.get("insured_city"),
                claim_fields.get("insured_state"),
                claim_fields.get("insured_zip"),
                claim_fields.get("policy_number"),
                claim_fields.get("secondary_insured_first"),
                claim_fields.get("secondary_insured_last"),
                claim_fields.get("loss_date"),
                claim_fields.get("loss_type"),
                claim_fields.get("loss_description"),
                claim_fields.get("loss_address1"),
                claim_fields.get("loss_city"),
                claim_fields.get("loss_state"),
                claim_fields.get("loss_zip"),
                claim_fields.get("client_company_name"),
                claim_fields.get("client_claim_number"),
                claim_fields.get("agent_company"),
                claim_fields.get("agent_phone"),
                claim_fields.get("agent_email"),
                claim_fields.get("agent_address1"),
                claim_fields.get("agent_city"),
                claim_fields.get("agent_state"),
                claim_fields.get("agent_zip"),
                claim_fields.get("assigned_adjuster_name"),
                claim_fields.get("policy_effective"),
                claim_fields.get("policy_expiration"),
                resolved.get("company_id"),
                resolved.get("contact_id"),
                resolved.get("branch_id"),
                resolved.get("adjuster_id"),
                resolved.get("manager_id"),
                resolved.get("csrf_token"),
                json.dumps(submission_payload) if submission_payload else None,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def get_history(self, limit: int = 50) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM processed_emails ORDER BY processed_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_app_config(self) -> dict:
        """Return submit_claim kwargs from the singleton app_config row."""
        defaults = {
            "dry_run": False,
            "test_mode": False,
            "test_adjuster_id": "342436",
            "test_branch_id": "2529",
        }
        try:
            row = self._conn.execute(
                "SELECT dry_run, test_mode, test_adjuster_id, test_branch_id "
                "FROM app_config WHERE id = 1"
            ).fetchone()
        except Exception:
            return defaults
        if row is None:
            return defaults
        return {
            "dry_run": bool(row["dry_run"]),
            "test_mode": bool(row["test_mode"]),
            "test_adjuster_id": row["test_adjuster_id"] or defaults["test_adjuster_id"],
            "test_branch_id": row["test_branch_id"] or defaults["test_branch_id"],
        }

    def is_poller_enabled(self) -> bool:
        """Return the poller_enabled flag. Defaults to True if column is absent."""
        try:
            row = self._conn.execute(
                "SELECT poller_enabled FROM app_config WHERE id = 1"
            ).fetchone()
            if row is None:
                return True
            return bool(row["poller_enabled"])
        except Exception:
            return True

    def update_poller_heartbeat(self, status: str) -> None:
        """Update poller_status and last_heartbeat timestamp."""
        now = datetime.now(timezone.utc).isoformat()
        try:
            self._conn.execute(
                "UPDATE app_config SET poller_status=?, last_heartbeat=? WHERE id=1",
                (status, now),
            )
            self._conn.commit()
        except Exception:
            pass  # Non-fatal — don't crash the poller over a status write

    def update_poller_run_result(self, error: str | None) -> None:
        """Update last_run_at and last_error after a poll cycle completes."""
        now = datetime.now(timezone.utc).isoformat()
        try:
            self._conn.execute(
                "UPDATE app_config SET last_run_at=?, last_error=? WHERE id=1",
                (now, error),
            )
            self._conn.commit()
        except Exception:
            pass

    def close(self) -> None:
        self._conn.close()
