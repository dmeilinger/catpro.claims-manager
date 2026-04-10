#!/usr/bin/env python3
"""
poller.py — Poll M365 shared mailbox for claim emails, process them, and
submit to FileTrac. Tracks all processed emails in SQLite.

Usage: python3.13 -m scripts.poll
"""

import json
import logging
import signal
import time
import traceback as tb
from datetime import datetime, timezone

from app.config import get_settings
from app.database import SessionLocal
from app.models import AppConfig, ClaimData as ClaimDataRow, EmailAction, ProcessedEmail
from app.services.email_source import EmailMessage, GraphMailSource, SkippedEmail
from app.services.filetrac_auth import build_session, login
from app.services.filetrac_submit import submit_claim
from app.services.pdf_extractor import extract_claim_fields

log = logging.getLogger("claim_poller")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Poller:
    def __init__(self) -> None:
        self._running = True
        self._settings = get_settings()
        self._source = GraphMailSource(
            tenant_id=self._settings.azure_tenant_id,
            client_id=self._settings.azure_client_id,
            client_secret=self._settings.azure_client_secret.get_secret_value(),
            mailbox=self._settings.m365_mailbox,
        )
        self._session = None

    def _ensure_session(self) -> None:
        """Lazily create and authenticate a FileTrac session."""
        if self._session is None:
            self._session = build_session()
            login(self._session)
            log.info("Authenticated to FileTrac")

    # ── Database helpers (SQLAlchemy) ─────────────────────────────────────────

    def _get_config(self) -> dict:
        with SessionLocal() as db:
            row = db.get(AppConfig, 1)
            if row is None:
                return {"dry_run": False, "test_mode": False,
                        "test_adjuster_id": "342436", "test_branch_id": "2529",
                        "test_company_id": "143898"}
            return {
                "dry_run": row.dry_run,
                "test_mode": row.test_mode,
                "test_adjuster_id": row.test_adjuster_id or "342436",
                "test_branch_id": row.test_branch_id or "2529",
                "test_company_id": "143898",
            }

    def _get_poll_interval(self) -> int:
        """Read poll_interval_seconds from DB so changes apply without restart."""
        try:
            with SessionLocal() as db:
                row = db.get(AppConfig, 1)
                if row is not None:
                    return row.poll_interval_seconds or 60
        except Exception:
            pass
        return self._settings.poll_interval_seconds

    def _is_duplicate(self, internet_message_id: str) -> bool:
        with SessionLocal() as db:
            return db.query(ProcessedEmail).filter_by(
                internet_message_id=internet_message_id
            ).first() is not None

    def _insert_pending(self, msg: EmailMessage) -> int:
        with SessionLocal() as db:
            row = ProcessedEmail(
                message_id=msg.message_id,
                internet_message_id=msg.internet_message_id,
                subject=msg.subject,
                sender=msg.sender,
                received_at=msg.received_at,
                processed_at=_now(),
                status="pending",
                triage_status="unreviewed",
                body_text=msg.body_text,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return row.id

    def _mark_success(self, row_id: int, claim_id: str) -> None:
        now = _now()
        with SessionLocal() as db:
            row = db.get(ProcessedEmail, row_id)
            if row:
                row.status = "success"
                row.claim_id = claim_id
                row.processed_at = now
                row.triage_status = "unreviewed"  # human review required; not auto-actioned
                db.add(EmailAction(
                    email_id=row_id,
                    action_type="created_claim",
                    actor="poller",
                    details=json.dumps({"claim_id": claim_id}),
                    created_at=now,
                ))
                db.commit()

    def _insert_skipped(self, item: SkippedEmail) -> None:
        """Record a skipped email in the DB so it isn't logged again next cycle."""
        with SessionLocal() as db:
            row = ProcessedEmail(
                message_id=item.message_id,
                internet_message_id=item.internet_message_id,
                subject=item.subject,
                sender=item.sender,
                received_at=item.received_at,
                processed_at=_now(),
                status="skipped",
                error_message=item.reason,
                dry_run=False,
                triage_status="unreviewed",
                body_text=item.body_text,
            )
            db.add(row)
            try:
                db.commit()
            except Exception:
                pass  # Already inserted by a concurrent cycle

    def _mark_error(
        self,
        row_id: int,
        error_message: str,
        error_traceback: str | None = None,
        error_phase: str | None = None,
    ) -> None:
        with SessionLocal() as db:
            row = db.get(ProcessedEmail, row_id)
            if row:
                row.status = "error"
                row.error_message = error_message
                row.error_traceback = error_traceback
                row.error_phase = error_phase
                row.processed_at = _now()
                row.triage_status = "needs_review"
                db.commit()

    def _insert_claim_data(
        self,
        email_id: int,
        claim_fields: dict,
        resolved_ids: dict | None = None,
        submission_payload: dict | None = None,
    ) -> None:
        resolved = resolved_ids or {}
        with SessionLocal() as db:
            row = ClaimDataRow(
                email_id=email_id,
                insured_first_name=claim_fields.get("insured_first_name"),
                insured_last_name=claim_fields.get("insured_last_name"),
                insured_email=claim_fields.get("insured_email"),
                insured_phone=claim_fields.get("insured_phone"),
                insured_cell=claim_fields.get("insured_cell"),
                insured_address1=claim_fields.get("insured_address1"),
                insured_city=claim_fields.get("insured_city"),
                insured_state=claim_fields.get("insured_state"),
                insured_zip=claim_fields.get("insured_zip"),
                secondary_insured_first=claim_fields.get("secondary_insured_first"),
                secondary_insured_last=claim_fields.get("secondary_insured_last"),
                policy_number=claim_fields.get("policy_number"),
                policy_effective=claim_fields.get("policy_effective"),
                policy_expiration=claim_fields.get("policy_expiration"),
                loss_date=claim_fields.get("loss_date"),
                loss_type=claim_fields.get("loss_type"),
                loss_description=claim_fields.get("loss_description"),
                loss_address1=claim_fields.get("loss_address1"),
                loss_city=claim_fields.get("loss_city"),
                loss_state=claim_fields.get("loss_state"),
                loss_zip=claim_fields.get("loss_zip"),
                client_company_name=claim_fields.get("client_company_name"),
                client_claim_number=claim_fields.get("client_claim_number"),
                agent_company=claim_fields.get("agent_company"),
                agent_phone=claim_fields.get("agent_phone"),
                agent_email=claim_fields.get("agent_email"),
                agent_address1=claim_fields.get("agent_address1"),
                agent_city=claim_fields.get("agent_city"),
                agent_state=claim_fields.get("agent_state"),
                agent_zip=claim_fields.get("agent_zip"),
                assigned_adjuster_name=claim_fields.get("assigned_adjuster_name"),
                filetrac_company_id=resolved.get("company_id"),
                filetrac_contact_id=resolved.get("contact_id"),
                filetrac_branch_id=resolved.get("branch_id"),
                filetrac_adjuster_id=resolved.get("adjuster_id"),
                filetrac_manager_id=resolved.get("manager_id"),
                filetrac_csrf_token=resolved.get("csrf_token"),
                submission_payload=json.dumps(submission_payload) if submission_payload else None,
                created_at=_now(),
            )
            db.add(row)
            db.commit()

    def _update_heartbeat(self, status: str) -> None:
        try:
            with SessionLocal() as db:
                row = db.get(AppConfig, 1)
                if row:
                    row.poller_status = status
                    row.last_heartbeat = _now()
                    db.commit()
        except Exception:
            pass  # Non-fatal — don't crash the poller over a status write

    def _update_run_result(self, error: str | None) -> None:
        try:
            with SessionLocal() as db:
                row = db.get(AppConfig, 1)
                if row:
                    row.last_run_at = _now()
                    row.last_error = error
                    db.commit()
        except Exception:
            pass

    # ── Poll logic ────────────────────────────────────────────────────────────

    def poll_once(self) -> None:
        """Single poll iteration: fetch unread → skip duplicates → process → update DB."""
        messages, skipped = self._source.fetch_unread()

        # Log and record newly-seen non-claim emails (once per email, permanently)
        for item in skipped:
            if self._is_duplicate(item.internet_message_id):
                continue
            log.info(
                "Skipping %r from %s — %s", item.subject, item.sender, item.reason
            )
            self._insert_skipped(item)

        if not messages:
            return

        log.info("Found %d unread message(s) with PDFs", len(messages))

        for msg in messages:
            if self._is_duplicate(msg.internet_message_id):
                log.info("Skipping duplicate: %s", msg.subject)
                self._source.mark_read(msg.message_id)
                continue

            row_id = self._insert_pending(msg)
            log.info("Processing: %s (row %d)", msg.subject, row_id)

            # Phase 1: Extract claim fields from email/PDF
            try:
                claim = extract_claim_fields(msg.body_text, msg.pdfs)
            except Exception as e:
                self._mark_error(row_id, str(e), tb.format_exc(), "extraction")
                log.error("Extraction failed: %s -> %s", msg.subject, e, exc_info=True)
                continue  # No claim_data to save; leave unread for manual review

            # Phase 2: Submit to FileTrac
            try:
                config = self._get_config()
                self._ensure_session()
                try:
                    result = submit_claim(self._session, claim, **config)
                except Exception:
                    # Session may have expired — re-auth and retry once
                    log.warning("Claim submission failed, re-authenticating...")
                    self._session = build_session()
                    login(self._session)
                    result = submit_claim(self._session, claim, **config)

                self._mark_success(row_id, result.claim_id)
                self._insert_claim_data(
                    email_id=row_id,
                    claim_fields=result.claim_fields,
                    resolved_ids=result.resolved_ids,
                    submission_payload=result.payload,
                )
                log.info("Success: %s -> %s", msg.subject, result.claim_id)
            except Exception as e:
                self._mark_error(row_id, str(e), tb.format_exc(), "submission")
                # Save partial data — extraction succeeded but submission failed
                self._insert_claim_data(email_id=row_id, claim_fields=claim.model_dump())
                log.error("Failed: %s -> %s", msg.subject, e, exc_info=True)
                continue  # Do NOT mark as read — leave for manual review

            try:
                self._source.mark_read(msg.message_id)
            except Exception as e:
                log.warning("Could not mark as read: %s -> %s", msg.subject, e)

    def run(self) -> None:
        """Main polling loop with graceful shutdown on SIGTERM/SIGINT."""
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "_running", False))
        signal.signal(signal.SIGINT, lambda *_: setattr(self, "_running", False))

        log.info(
            "Starting poller (interval=%ds, mailbox=%s)",
            self._get_poll_interval(),
            self._settings.m365_mailbox,
        )

        while self._running:
            try:
                self._update_heartbeat("running")
                self.poll_once()
                self._update_run_result(None)
            except Exception as e:
                log.error("Poll cycle error: %s", e, exc_info=True)
                self._update_run_result(str(e))

            # Interruptible sleep — re-reads interval from DB each second so
            # config changes take effect immediately without restarting.
            elapsed = 0
            while self._running:
                interval = self._get_poll_interval()
                if elapsed >= interval:
                    break
                time.sleep(1)
                elapsed += 1

        self._update_heartbeat("stopped")
        log.info("Poller stopped")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    Poller().run()


if __name__ == "__main__":
    main()
