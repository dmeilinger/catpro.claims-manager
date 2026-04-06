"""TDD tests for Phase 3: inbox/email-log endpoints, CORS, stats, sort_by fix."""

import json
import uuid
import pytest
from app.models import EmailAction, ProcessedEmail


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_email(db, *, status="pending", triage_status="unreviewed",
                subject="Test", sender="s@example.com", claim_id=None,
                dry_run=False, error_message=None) -> ProcessedEmail:
    uid = uuid.uuid4().hex[:8]
    row = ProcessedEmail(
        message_id=f"msg-{uid}",
        internet_message_id=f"<{uid}@test>",
        subject=subject,
        sender=sender,
        received_at="2026-04-05T10:00:00",
        processed_at="2026-04-05T10:01:00",
        status=status,
        triage_status=triage_status,
        claim_id=claim_id,
        dry_run=dry_run,
        error_message=error_message,
    )
    db.add(row)
    db.flush()
    return row


# ── CORS ─────────────────────────────────────────────────────────────────────

class TestCORS:
    def test_cors_allows_patch(self, client):
        resp = client.options(
            "/api/v1/inbox/count",
            headers={
                "Origin": "http://localhost:5175",
                "Access-Control-Request-Method": "PATCH",
            },
        )
        allowed = resp.headers.get("access-control-allow-methods", "")
        assert "PATCH" in allowed

    def test_cors_allows_post(self, client):
        resp = client.options(
            "/api/v1/inbox/count",
            headers={
                "Origin": "http://localhost:5175",
                "Access-Control-Request-Method": "POST",
            },
        )
        allowed = resp.headers.get("access-control-allow-methods", "")
        assert "POST" in allowed

    def test_cors_allows_delete(self, client):
        resp = client.options(
            "/api/v1/inbox/count",
            headers={
                "Origin": "http://localhost:5175",
                "Access-Control-Request-Method": "DELETE",
            },
        )
        allowed = resp.headers.get("access-control-allow-methods", "")
        assert "DELETE" in allowed


# ── GET /inbox/count ─────────────────────────────────────────────────────────

class TestInboxCount:
    def test_returns_count_of_needs_review(self, client, db):
        _make_email(db, triage_status="needs_review")
        _make_email(db, triage_status="needs_review")
        _make_email(db, triage_status="unreviewed")
        _make_email(db, triage_status="actioned")

        resp = client.get("/api/v1/inbox/count")
        assert resp.status_code == 200
        assert resp.json()["count"] == 2

    def test_returns_zero_when_empty(self, client, db):
        resp = client.get("/api/v1/inbox/count")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0


# ── GET /inbox ────────────────────────────────────────────────────────────────

class TestInbox:
    def test_returns_only_needs_review(self, client, db):
        _make_email(db, triage_status="needs_review", subject="Error Email")
        _make_email(db, triage_status="unreviewed", subject="Not in inbox")
        _make_email(db, triage_status="actioned", subject="Also not in inbox")

        resp = client.get("/api/v1/inbox")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["subject"] == "Error Email"

    def test_returns_paginated_envelope(self, client, db):
        for i in range(3):
            _make_email(db, triage_status="needs_review", subject=f"Email {i}")

        resp = client.get("/api/v1/inbox?page=1&page_size=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 2
        assert data["page"] == 1
        assert data["page_size"] == 2

    def test_items_include_triage_status(self, client, db):
        _make_email(db, triage_status="needs_review")
        resp = client.get("/api/v1/inbox")
        assert resp.json()["items"][0]["triage_status"] == "needs_review"


# ── GET /email-log ────────────────────────────────────────────────────────────

class TestEmailLog:
    def test_returns_all_emails(self, client, db):
        for status in ["success", "error", "skipped", "pending"]:
            _make_email(db, status=status)

        resp = client.get("/api/v1/email-log")
        assert resp.status_code == 200
        assert resp.json()["total"] == 4

    def test_filter_by_status(self, client, db):
        _make_email(db, status="success")
        _make_email(db, status="error")

        resp = client.get("/api/v1/email-log?status=error")
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["status"] == "error"

    def test_filter_by_triage_status(self, client, db):
        _make_email(db, triage_status="needs_review")
        _make_email(db, triage_status="unreviewed")

        resp = client.get("/api/v1/email-log?triage_status=needs_review")
        data = resp.json()
        assert data["total"] == 1

    def test_stats_single_group_by(self, client, db):
        """Stats come from a single GROUP BY query — verify all fields present."""
        _make_email(db, status="success", dry_run=False)
        _make_email(db, status="success", dry_run=True)
        _make_email(db, status="error")
        _make_email(db, status="skipped")

        resp = client.get("/api/v1/email-log")
        stats = resp.json()["stats"]
        assert stats["total"] == 4
        assert stats["success"] == 1  # success AND NOT dry_run
        assert stats["dry_run"] == 1
        assert stats["error"] == 1
        assert stats["skipped"] == 1
        assert "needs_review" not in stats  # intentionally omitted

    def test_search_by_subject(self, client, db):
        _make_email(db, subject="Fw: TG4832 Acuity")
        _make_email(db, subject="Fw: TG0001 Different")

        resp = client.get("/api/v1/email-log?search=TG4832")
        assert resp.json()["total"] == 1

    def test_search_by_sender(self, client, db):
        _make_email(db, sender="acuity@claims.com")
        _make_email(db, sender="other@claims.com")

        resp = client.get("/api/v1/email-log?search=acuity")
        assert resp.json()["total"] == 1

    def test_includes_triage_status_in_items(self, client, db):
        _make_email(db, triage_status="actioned")
        resp = client.get("/api/v1/email-log")
        assert "triage_status" in resp.json()["items"][0]


# ── GET /email-log/{id} ───────────────────────────────────────────────────────

class TestEmailLogDetail:
    def test_returns_email_detail(self, client, db):
        row = _make_email(db)
        resp = client.get(f"/api/v1/email-log/{row.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == row.id
        assert "actions" in data

    def test_returns_404_for_unknown_id(self, client, db):
        resp = client.get("/api/v1/email-log/99999")
        assert resp.status_code == 404

    def test_actions_included_in_detail(self, client, db):
        row = _make_email(db)
        db.add(EmailAction(
            email_id=row.id,
            action_type="created_claim",
            actor="poller",
            details=json.dumps({"claim_id": "123"}),
            created_at="2026-04-05T10:01:00",
        ))
        db.flush()

        resp = client.get(f"/api/v1/email-log/{row.id}")
        data = resp.json()
        assert len(data["actions"]) == 1
        assert data["actions"][0]["action_type"] == "created_claim"
        assert data["actions"][0]["details"] == {"claim_id": "123"}  # parsed from JSON

    def test_action_details_parsed_as_dict(self, client, db):
        """details stored as JSON string must be returned as dict."""
        row = _make_email(db)
        db.add(EmailAction(
            email_id=row.id,
            action_type="flagged_review",
            actor="admin",
            details=json.dumps({"note": "weird email"}),
            created_at="2026-04-05T10:02:00",
        ))
        db.flush()

        resp = client.get(f"/api/v1/email-log/{row.id}")
        action = resp.json()["actions"][0]
        assert isinstance(action["details"], dict)
        assert action["details"]["note"] == "weird email"


# ── PATCH /email-log/{id}/triage ─────────────────────────────────────────────

class TestTriageAction:
    def test_flag_review_sets_needs_review(self, client, db):
        row = _make_email(db, triage_status="unreviewed")
        resp = client.patch(f"/api/v1/email-log/{row.id}/triage",
                            json={"action": "flag_review"})
        assert resp.status_code == 200
        assert resp.json()["triage_status"] == "needs_review"

    def test_dismiss_sets_actioned(self, client, db):
        row = _make_email(db, triage_status="needs_review")
        resp = client.patch(f"/api/v1/email-log/{row.id}/triage",
                            json={"action": "dismiss"})
        assert resp.status_code == 200
        assert resp.json()["triage_status"] == "actioned"

    def test_approve_sets_actioned(self, client, db):
        row = _make_email(db, triage_status="needs_review")
        resp = client.patch(f"/api/v1/email-log/{row.id}/triage",
                            json={"action": "approve"})
        assert resp.status_code == 200
        assert resp.json()["triage_status"] == "actioned"

    def test_invalid_action_returns_422(self, client, db):
        row = _make_email(db)
        resp = client.patch(f"/api/v1/email-log/{row.id}/triage",
                            json={"action": "delete_everything"})
        assert resp.status_code == 422

    def test_actor_hardcoded_to_admin(self, client, db):
        row = _make_email(db)
        client.patch(f"/api/v1/email-log/{row.id}/triage",
                     json={"action": "flag_review"})
        db.expire_all()
        action = db.query(EmailAction).filter_by(email_id=row.id).first()
        assert action is not None
        assert action.actor == "admin"

    def test_action_logged_to_email_actions(self, client, db):
        row = _make_email(db)
        client.patch(f"/api/v1/email-log/{row.id}/triage",
                     json={"action": "dismiss"})
        db.expire_all()
        actions = db.query(EmailAction).filter_by(email_id=row.id).all()
        assert len(actions) == 1
        assert actions[0].action_type == "dismiss"

    def test_returns_404_for_unknown_id(self, client, db):
        resp = client.patch("/api/v1/email-log/99999/triage",
                            json={"action": "dismiss"})
        assert resp.status_code == 404

    def test_response_includes_action_timeline(self, client, db):
        row = _make_email(db)
        resp = client.patch(f"/api/v1/email-log/{row.id}/triage",
                            json={"action": "approve"})
        data = resp.json()
        assert "actions" in data
        assert len(data["actions"]) == 1


# ── sort_by allowlist (pre-existing bug) ─────────────────────────────────────

class TestSortByAllowlist:
    def test_valid_sort_by_processed_at(self, client, db):
        _make_email(db)
        resp = client.get("/api/v1/claims?sort_by=processed_at")
        assert resp.status_code == 200

    def test_invalid_sort_by_uses_safe_fallback(self, client, db):
        """sort_by with an unsafe column name must not raise AttributeError."""
        _make_email(db)
        resp = client.get("/api/v1/claims?sort_by=__class__")
        assert resp.status_code == 200  # safe fallback, not 500
