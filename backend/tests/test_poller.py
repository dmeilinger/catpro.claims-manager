"""TDD tests for Phase 5: poller triage_status + body_text storage."""

import json
import pytest
from unittest.mock import patch

from app.models import EmailAction, ProcessedEmail
from app.services.email_source import EmailMessage, SkippedEmail


# ── Session patching helper ───────────────────────────────────────────────────

class _FakeSessionFactory:
    """Stands in for SessionLocal — yields the test session via context manager."""

    def __init__(self, session):
        self._session = session

    def __call__(self):
        return self

    def __enter__(self):
        return self._session

    def __exit__(self, *args):
        # Do NOT commit/close — the test fixture handles rollback.
        return False


@pytest.fixture()
def poller(db):
    """Poller instance with SessionLocal patched to use the test db session."""
    from app.services.poller import Poller
    p = Poller.__new__(Poller)
    p._settings = None
    p._source = None
    p._session = None
    p._running = True
    p._fake_session = _FakeSessionFactory(db)
    return p


def _patch_session(poller):
    return patch("app.services.poller.SessionLocal", poller._fake_session)


# ── SkippedEmail.body_text field ──────────────────────────────────────────────

class TestSkippedEmailBodyText:
    def test_skipped_email_has_body_text_field(self):
        """SkippedEmail NamedTuple must include body_text."""
        item = SkippedEmail(
            message_id="m1",
            internet_message_id="<m1@test>",
            subject="Test",
            sender="s@s.com",
            received_at="2026-04-05T10:00:00",
            reason="no attachments",
            body_text="Hello from the email body.",
        )
        assert item.body_text == "Hello from the email body."

    def test_skipped_email_body_text_default_empty(self):
        """body_text should be an accessible field (not a surprise attribute error)."""
        item = SkippedEmail(
            message_id="m2",
            internet_message_id="<m2@test>",
            subject="Subj",
            sender="s@s.com",
            received_at="2026-04-05T10:00:00",
            reason="no PDF",
            body_text="",
        )
        assert item.body_text == ""


# ── _insert_pending ──────────────────────────────────────────────────────────

class TestInsertPending:
    def _make_msg(self, body_text="Body text here."):
        return EmailMessage(
            message_id="msg-pending-1",
            internet_message_id="<pending1@test>",
            subject="Fw: TG1234",
            sender="noreply@acuity.com",
            received_at="2026-04-05T10:00:00",
            body_text=body_text,
            pdfs={},
        )

    def test_sets_triage_status_unreviewed(self, db, poller):
        with _patch_session(poller):
            row_id = poller._insert_pending(self._make_msg())
        row = db.get(ProcessedEmail, row_id)
        assert row.triage_status == "unreviewed"

    def test_stores_body_text(self, db, poller):
        with _patch_session(poller):
            row_id = poller._insert_pending(self._make_msg("Specific body content."))
        row = db.get(ProcessedEmail, row_id)
        assert row.body_text == "Specific body content."

    def test_status_is_pending(self, db, poller):
        with _patch_session(poller):
            row_id = poller._insert_pending(self._make_msg())
        row = db.get(ProcessedEmail, row_id)
        assert row.status == "pending"


# ── _mark_success ────────────────────────────────────────────────────────────

class TestMarkSuccess:
    def _insert_row(self, db) -> int:
        row = ProcessedEmail(
            message_id="msg-s1",
            internet_message_id="<s1@test>",
            subject="Test",
            sender="s@s.com",
            received_at="2026-04-05T10:00:00",
            processed_at="2026-04-05T10:00:00",
            status="pending",
        )
        db.add(row)
        db.flush()
        return row.id

    def test_sets_triage_status_unreviewed_not_actioned(self, db, poller):
        row_id = self._insert_row(db)
        with _patch_session(poller):
            poller._mark_success(row_id, "claimID=99999")
        db.expire_all()
        row = db.get(ProcessedEmail, row_id)
        assert row.triage_status == "unreviewed"

    def test_inserts_created_claim_email_action(self, db, poller):
        row_id = self._insert_row(db)
        with _patch_session(poller):
            poller._mark_success(row_id, "claimID=99999")
        db.expire_all()
        actions = db.query(EmailAction).filter_by(email_id=row_id).all()
        assert len(actions) == 1
        assert actions[0].action_type == "created_claim"
        assert actions[0].actor == "poller"

    def test_action_details_contains_claim_id(self, db, poller):
        row_id = self._insert_row(db)
        with _patch_session(poller):
            poller._mark_success(row_id, "claimID=99999")
        db.expire_all()
        action = db.query(EmailAction).filter_by(email_id=row_id).first()
        details = json.loads(action.details)
        assert details["claim_id"] == "claimID=99999"

    def test_sets_status_success(self, db, poller):
        row_id = self._insert_row(db)
        with _patch_session(poller):
            poller._mark_success(row_id, "claimID=99999")
        db.expire_all()
        row = db.get(ProcessedEmail, row_id)
        assert row.status == "success"


# ── _mark_error ──────────────────────────────────────────────────────────────

class TestMarkError:
    def _insert_row(self, db) -> int:
        row = ProcessedEmail(
            message_id="msg-e1",
            internet_message_id="<e1@test>",
            subject="Test",
            sender="s@s.com",
            received_at="2026-04-05T10:00:00",
            processed_at="2026-04-05T10:00:00",
            status="pending",
        )
        db.add(row)
        db.flush()
        return row.id

    def test_sets_triage_status_needs_review(self, db, poller):
        row_id = self._insert_row(db)
        with _patch_session(poller):
            poller._mark_error(row_id, "CompanyID not found")
        db.expire_all()
        row = db.get(ProcessedEmail, row_id)
        assert row.triage_status == "needs_review"

    def test_sets_status_error(self, db, poller):
        row_id = self._insert_row(db)
        with _patch_session(poller):
            poller._mark_error(row_id, "Something went wrong")
        db.expire_all()
        row = db.get(ProcessedEmail, row_id)
        assert row.status == "error"
        assert row.error_message == "Something went wrong"


# ── _insert_skipped ──────────────────────────────────────────────────────────

class TestInsertSkipped:
    def _make_skipped(self, body_text="Skipped body."):
        return SkippedEmail(
            message_id="msg-sk1",
            internet_message_id="<sk1@test>",
            subject="Fwd: Invoice",
            sender="billing@example.com",
            received_at="2026-04-05T10:00:00",
            reason="no PDF attachments",
            body_text=body_text,
        )

    def test_sets_triage_status_unreviewed(self, db, poller):
        with _patch_session(poller):
            poller._insert_skipped(self._make_skipped())
        row = db.query(ProcessedEmail).filter_by(
            internet_message_id="<sk1@test>"
        ).first()
        assert row is not None
        assert row.triage_status == "unreviewed"

    def test_stores_body_text(self, db, poller):
        with _patch_session(poller):
            poller._insert_skipped(self._make_skipped("Skipped email body content."))
        row = db.query(ProcessedEmail).filter_by(
            internet_message_id="<sk1@test>"
        ).first()
        assert row.body_text == "Skipped email body content."

    def test_status_is_skipped(self, db, poller):
        with _patch_session(poller):
            poller._insert_skipped(self._make_skipped())
        row = db.query(ProcessedEmail).filter_by(
            internet_message_id="<sk1@test>"
        ).first()
        assert row.status == "skipped"
