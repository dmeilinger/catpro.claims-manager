"""TDD tests for Phase 1: triage_status, body_text, EmailAction model."""

import json
import pytest
from sqlalchemy import inspect, text

from app.models import EmailAction, ProcessedEmail


def _make_email(session, **kwargs) -> ProcessedEmail:
    defaults = dict(
        message_id="msg-1",
        internet_message_id="<msg1@test>",
        subject="Test",
        sender="test@example.com",
        received_at="2026-04-05T10:00:00",
        processed_at="2026-04-05T10:01:00",
        status="pending",
    )
    defaults.update(kwargs)
    row = ProcessedEmail(**defaults)
    session.add(row)
    session.flush()
    return row


class TestProcessedEmailNewColumns:
    def test_triage_status_default_is_unreviewed(self, db):
        row = _make_email(db)
        assert row.triage_status == "unreviewed"

    def test_triage_status_can_be_set(self, db):
        row = _make_email(db, triage_status="needs_review")
        assert row.triage_status == "needs_review"

    def test_body_text_nullable(self, db):
        row = _make_email(db)
        assert row.body_text is None

    def test_body_text_stores_content(self, db):
        row = _make_email(db, body_text="Email body content here.")
        assert row.body_text == "Email body content here."

    def test_triage_status_column_exists_in_db(self, db):
        inspector = inspect(db.get_bind())
        cols = {c["name"] for c in inspector.get_columns("processed_emails")}
        assert "triage_status" in cols
        assert "body_text" in cols


class TestEmailActionModel:
    def test_create_action(self, db):
        email = _make_email(db)
        action = EmailAction(
            email_id=email.id,
            action_type="created_claim",
            actor="poller",
            details=json.dumps({"claim_id": "12345"}),
            created_at="2026-04-05T10:01:00",
        )
        db.add(action)
        db.flush()
        assert action.id is not None
        assert action.action_type == "created_claim"
        assert action.actor == "poller"

    def test_email_actions_relationship(self, db):
        email = _make_email(db)
        for action_type in ["created_claim", "flagged_review"]:
            db.add(EmailAction(
                email_id=email.id,
                action_type=action_type,
                actor="poller",
                created_at="2026-04-05T10:01:00",
            ))
        db.flush()
        db.refresh(email)
        assert len(email.actions) == 2
        assert email.actions[0].action_type == "created_claim"

    def test_email_action_back_ref(self, db):
        email = _make_email(db)
        action = EmailAction(
            email_id=email.id,
            action_type="dismiss",
            actor="admin",
            created_at="2026-04-05T10:02:00",
        )
        db.add(action)
        db.flush()
        assert action.email.id == email.id

    def test_action_details_nullable(self, db):
        email = _make_email(db)
        action = EmailAction(
            email_id=email.id,
            action_type="approve",
            actor="admin",
            details=None,
            created_at="2026-04-05T10:03:00",
        )
        db.add(action)
        db.flush()
        assert action.details is None

    def test_email_actions_table_exists(self, db):
        inspector = inspect(db.get_bind())
        assert "email_actions" in inspector.get_table_names()

    def test_foreign_key_enforced(self, db):
        """FK to processed_emails.id — inserting with nonexistent email_id raises."""
        action = EmailAction(
            email_id=99999,
            action_type="approve",
            actor="admin",
            created_at="2026-04-05T10:03:00",
        )
        db.add(action)
        with pytest.raises(Exception):
            db.flush()
