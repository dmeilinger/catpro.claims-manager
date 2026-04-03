#!/usr/bin/env python3
"""
poller.py — Poll M365 shared mailbox for claim emails, process them, and
submit to FileTrac. Tracks all processed emails in SQLite.

Usage: python3.13 poller.py
"""

import logging
import signal
import time

from catpro.config import get_settings
from catpro.db import ClaimDatabase
from catpro.email_source import EmailMessage, GraphMailSource
from catpro.process_claim import build_session, extract_claim_fields, login, submit_claim

log = logging.getLogger("claim_poller")


class Poller:
    def __init__(self) -> None:
        self._running = True
        self._settings = get_settings()
        self._db = ClaimDatabase(self._settings.db_path)
        self._source = GraphMailSource(
            tenant_id=self._settings.azure_tenant_id,
            client_id=self._settings.azure_client_id,
            client_secret=self._settings.azure_client_secret,
            mailbox=self._settings.m365_mailbox,
        )
        self._session = None

    def _ensure_session(self) -> None:
        """Lazily create and authenticate a FileTrac session."""
        if self._session is None:
            self._session = build_session()
            login(self._session)
            log.info("Authenticated to FileTrac")

    def _process_message(self, msg: EmailMessage):
        """Process a single email through the claim pipeline. Returns SubmitResult."""
        claim = extract_claim_fields(msg.body_text, msg.pdfs)
        cfg = self._db.get_app_config()
        self._ensure_session()
        try:
            return submit_claim(self._session, claim, **cfg)
        except Exception:
            # Session may have expired — re-auth and retry once
            log.warning("Claim submission failed, re-authenticating...")
            self._session = build_session()
            login(self._session)
            return submit_claim(self._session, claim, **cfg)

    def poll_once(self) -> None:
        """Single poll iteration: fetch unread → skip duplicates → process → update DB."""
        messages = self._source.fetch_unread()
        if not messages:
            return

        log.info("Found %d unread message(s) with PDFs", len(messages))

        for msg in messages:
            if self._db.is_duplicate(msg.internet_message_id):
                log.info("Skipping duplicate: %s", msg.subject)
                self._source.mark_read(msg.message_id)
                continue

            row_id = self._db.insert_pending(
                msg.message_id,
                msg.internet_message_id,
                msg.subject,
                msg.sender,
                msg.received_at,
            )
            log.info("Processing: %s (row %d)", msg.subject, row_id)

            try:
                result = self._process_message(msg)
                self._db.mark_success(row_id, result.claim_id)
                self._db.insert_claim_data(
                    email_id=row_id,
                    claim_fields=result.claim_fields,
                    resolved_ids=result.resolved_ids,
                    submission_payload=result.payload,
                )
                log.info("Success: %s -> %s", msg.subject, result.claim_id)
            except Exception as e:
                self._db.mark_error(row_id, str(e))
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
            self._settings.poll_interval_seconds,
            self._settings.m365_mailbox,
        )

        while self._running:
            try:
                self.poll_once()
            except Exception as e:
                log.error("Poll cycle error: %s", e, exc_info=True)

            # Interruptible sleep — checks _running every second for clean shutdown
            for _ in range(self._settings.poll_interval_seconds):
                if not self._running:
                    break
                time.sleep(1)

        self._db.close()
        log.info("Poller stopped")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    Poller().run()


if __name__ == "__main__":
    main()
