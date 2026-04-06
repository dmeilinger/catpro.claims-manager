"""TDD tests for Phase 2: two-phase Graph fetch + @odata.nextLink pagination."""

import base64
import json
from unittest.mock import MagicMock, call, patch

import pytest

from app.services.email_source import EmailMessage, GraphMailSource, SkippedEmail


def _make_source() -> GraphMailSource:
    with patch("msal.ConfidentialClientApplication"):
        source = GraphMailSource(
            tenant_id="tenant-id",
            client_id="client-id",
            client_secret="secret",
            mailbox="claims@example.com",
        )
    source._token = "fake-token"
    return source


def _make_msg(
    msg_id: str = "msg1",
    subject: str = "Fw: TG1234",
    sender: str = "noreply@acuity.com",
    has_attachments: bool = True,
    body_html: str = "<p>Hello</p>",
    internet_message_id: str = "<msg1@test>",
) -> dict:
    return {
        "id": msg_id,
        "internetMessageId": internet_message_id,
        "subject": subject,
        "from": {"emailAddress": {"address": sender}},
        "receivedDateTime": "2026-04-05T10:00:00Z",
        "body": {"content": body_html, "contentType": "html"},
        "hasAttachments": has_attachments,
    }


def _pdf_attachment(name: str = "claim.pdf") -> dict:
    return {
        "contentType": "application/pdf",
        "name": name,
        "contentBytes": base64.b64encode(b"%PDF-1.4 fake").decode(),
    }


def _non_pdf_attachment(name: str = "logo.png") -> dict:
    return {
        "contentType": "image/png",
        "name": name,
        "contentBytes": base64.b64encode(b"\x89PNG fake").decode(),
    }


# ── Two-phase fetch ───────────────────────────────────────────────────────────

class TestTwoPhaseMessageFetch:
    """Phase 1 (metadata) must NOT use $expand=attachments.
    Phase 2 (attachments) fetched separately per message."""

    def test_metadata_request_has_no_expand(self):
        """The first GET must not include $expand=attachments."""
        source = _make_source()

        with patch.object(source, "_request") as mock_req:
            # Return empty result so we don't process any messages
            mock_req.return_value.json.return_value = {"value": []}
            source.fetch_unread()

        first_call_url = mock_req.call_args_list[0][0][1]
        assert "$expand" not in first_call_url

    def test_metadata_request_selects_has_attachments(self):
        """$select must include hasAttachments so we know when to fetch phase 2."""
        source = _make_source()

        with patch.object(source, "_request") as mock_req:
            mock_req.return_value.json.return_value = {"value": []}
            source.fetch_unread()

        first_call_url = mock_req.call_args_list[0][0][1]
        assert "hasAttachments" in first_call_url

    def test_phase2_fetch_called_for_has_attachments_true(self):
        """When hasAttachments=true, a second GET to /attachments must be made."""
        source = _make_source()
        msg = _make_msg(has_attachments=True)

        attachment_resp = MagicMock()
        attachment_resp.json.return_value = {"value": [_pdf_attachment()]}

        with patch.object(source, "_request") as mock_req:
            mock_req.side_effect = [
                MagicMock(**{"json.return_value": {"value": [msg]}}),
                attachment_resp,
            ]
            source.fetch_unread()

        assert mock_req.call_count == 2
        second_url = mock_req.call_args_list[1][0][1]
        assert "attachments" in second_url
        assert msg["id"] in second_url

    def test_phase2_not_called_for_has_attachments_false(self):
        """When hasAttachments=false, no attachment fetch should occur."""
        source = _make_source()
        msg = _make_msg(has_attachments=False)

        with patch.object(source, "_request") as mock_req:
            mock_req.return_value.json.return_value = {"value": [msg]}
            source.fetch_unread()

        # Only one call — the metadata request
        assert mock_req.call_count == 1

    def test_message_with_pdf_returned_in_messages(self):
        source = _make_source()
        msg = _make_msg(has_attachments=True)

        with patch.object(source, "_request") as mock_req:
            mock_req.side_effect = [
                MagicMock(**{"json.return_value": {"value": [msg]}}),
                MagicMock(**{"json.return_value": {"value": [_pdf_attachment()]}}),
            ]
            messages, skipped = source.fetch_unread()

        assert len(messages) == 1
        assert len(skipped) == 0
        assert messages[0].subject == "Fw: TG1234"

    def test_body_text_extracted_from_html(self):
        source = _make_source()
        msg = _make_msg(has_attachments=True, body_html="<p>Hello <b>world</b></p>")

        with patch.object(source, "_request") as mock_req:
            mock_req.side_effect = [
                MagicMock(**{"json.return_value": {"value": [msg]}}),
                MagicMock(**{"json.return_value": {"value": [_pdf_attachment()]}}),
            ]
            messages, _ = source.fetch_unread()

        assert "Hello" in messages[0].body_text
        assert "<p>" not in messages[0].body_text  # HTML stripped

    def test_skipped_email_body_text_populated(self):
        """Skipped emails (no attachments) must have body_text set."""
        source = _make_source()
        msg = _make_msg(has_attachments=False, body_html="<p>No PDF here</p>")

        with patch.object(source, "_request") as mock_req:
            mock_req.return_value.json.return_value = {"value": [msg]}
            _, skipped = source.fetch_unread()

        assert len(skipped) == 1
        assert "No PDF here" in skipped[0].body_text

    def test_non_pdf_attachment_produces_skipped(self):
        source = _make_source()
        msg = _make_msg(has_attachments=True)

        with patch.object(source, "_request") as mock_req:
            mock_req.side_effect = [
                MagicMock(**{"json.return_value": {"value": [msg]}}),
                MagicMock(**{"json.return_value": {"value": [_non_pdf_attachment()]}}),
            ]
            messages, skipped = source.fetch_unread()

        assert len(messages) == 0
        assert len(skipped) == 1
        assert "no pdf" in skipped[0].reason.lower()


# ── @odata.nextLink pagination ────────────────────────────────────────────────

class TestNextLinkPagination:
    def test_follows_next_link(self):
        """When @odata.nextLink present, fetches next page."""
        source = _make_source()

        page1 = {
            "value": [_make_msg("msg1", internet_message_id="<m1@t>")],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/next-page",
        }
        page2 = {"value": []}  # Empty = done

        with patch.object(source, "_request") as mock_req:
            mock_req.side_effect = [
                MagicMock(**{"json.return_value": page1}),
                MagicMock(**{"json.return_value": {"value": [_pdf_attachment()]}}),
                MagicMock(**{"json.return_value": page2}),
            ]
            messages, _ = source.fetch_unread()

        # nextLink call uses the full URL from the response
        calls = [c[0][1] for c in mock_req.call_args_list]
        assert any("next-page" in url for url in calls)

    def test_next_link_uses_self_request_not_raw_http(self):
        """CRITICAL: nextLink must go through self._request() for 401 token refresh."""
        source = _make_source()

        page1 = {
            "value": [],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/next-page",
        }
        page2 = {"value": []}

        with patch.object(source, "_request") as mock_req:
            mock_req.side_effect = [
                MagicMock(**{"json.return_value": page1}),
                MagicMock(**{"json.return_value": page2}),
            ]
            source.fetch_unread()

        # Both calls must go through _request — not raw http_requests
        assert mock_req.call_count == 2

    def test_page_cap_prevents_runaway_pagination(self):
        """Should stop after MAX_PAGES even if nextLink keeps appearing."""
        source = _make_source()

        infinite_page = {
            "value": [],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/next-page",
        }

        with patch.object(source, "_request") as mock_req:
            mock_req.return_value.json.return_value = infinite_page
            source.fetch_unread()

        # Must stop at exactly MAX_PAGES (20), not more
        assert mock_req.call_count == 20

    def test_top_50_in_initial_url(self):
        """Initial fetch must use $top=50 (not $top=10)."""
        source = _make_source()

        with patch.object(source, "_request") as mock_req:
            mock_req.return_value.json.return_value = {"value": []}
            source.fetch_unread()

        first_url = mock_req.call_args_list[0][0][1]
        assert "$top=50" in first_url
        assert "$top=10" not in first_url

    def test_multiple_messages_across_pages(self):
        """Messages from all pages are collected into one list."""
        source = _make_source()

        msg1 = _make_msg("id1", internet_message_id="<m1@t>", has_attachments=True)
        msg2 = _make_msg("id2", internet_message_id="<m2@t>", has_attachments=True)

        page1 = {"value": [msg1], "@odata.nextLink": "https://graph.microsoft.com/v1.0/p2"}
        page2 = {"value": [msg2]}

        with patch.object(source, "_request") as mock_req:
            mock_req.side_effect = [
                MagicMock(**{"json.return_value": page1}),
                MagicMock(**{"json.return_value": {"value": [_pdf_attachment()]}}),  # msg1 attachments
                MagicMock(**{"json.return_value": page2}),
                MagicMock(**{"json.return_value": {"value": [_pdf_attachment()]}}),  # msg2 attachments
            ]
            messages, _ = source.fetch_unread()

        assert len(messages) == 2
