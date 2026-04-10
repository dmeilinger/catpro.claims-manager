"""Tests for filetrac_submit.py — submit_claim modes and payload construction.

Coverage focus: the sandbox update mode (existing_claim_id), hardened test mode
overrides (company/contact/email suppression), and dry-run behaviour added in
the feat/mailbox-case-management branch.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.services.filetrac_submit import (
    CLAIM_EDIT_URL,
    CLAIM_FORM_URL,
    CLAIM_SAVE_URL,
    CLAIM_UPDATE_URL,
    COMPANY_AUTOCOMPLETE_URL,
    submit_claim,
)
from app.services.pdf_extractor import ClaimData


# ── Fixtures ──────────────────────────────────────────────────────────────────

# Minimal HTML that satisfies extract_csrf_token + _parse_select_first_value
_FORM_HTML = """
<html><body>
<input type="hidden" name="pageLayout_CSRtoken" value="csrf-tok-abc123">
<select name="ACmgrID">
  <option value="-1">Select</option>
  <option value="319972">Doug Hubby</option>
</select>
</body></html>
"""

_COMPANY_XML = "<rs id='99999' info='Test Company'/>"
_REPS_TEXT = "##/##TestCo##rep@test.com##foo~12345##Rep Name"
_BRANCHES_TEXT = "5555##Main Branch"

# Minimal ClaimData with enough fields to build a payload
_CLAIM = ClaimData(
    insured_first_name="John",
    insured_last_name="Doe",
    policy_number="POL-123",
    loss_date="1/1/2026",
    loss_type="Hail",
    client_company_name="Test Company",
    client_claim_number="TG0001",
    assigned_adjuster_name="",
)


def _mock_session(post_html="<!-- claimID = [9999999] -->"):
    """Build a mock requests.Session with canned GET/POST responses."""
    session = MagicMock()

    def _get(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        params = kwargs.get("params", {})
        if url in (CLAIM_FORM_URL, CLAIM_EDIT_URL):
            resp.text = _FORM_HTML
        elif params.get("mode") == "customerCompanies":
            resp.text = _COMPANY_XML
        elif params.get("mode") == "customerReps":
            resp.text = _REPS_TEXT
        elif params.get("mode") == "customerBranches":
            resp.text = _BRANCHES_TEXT
        else:
            resp.text = ""
        return resp

    post_resp = MagicMock()
    post_resp.raise_for_status = MagicMock()
    post_resp.text = post_html
    post_resp.url = "https://cms14.filetrac.net/system/claimList.asp"

    session.get = MagicMock(side_effect=_get)
    session.post = MagicMock(return_value=post_resp)
    return session


# ── Dry-run ───────────────────────────────────────────────────────────────────

class TestDryRun:
    """dry_run=True must return DRY_RUN without POSTing."""

    def test_no_post_on_dry_run(self):
        session = _mock_session()
        result = submit_claim(session, _CLAIM, dry_run=True)
        session.post.assert_not_called()
        assert result.claim_id == "DRY_RUN"

    def test_payload_is_populated(self):
        session = _mock_session()
        result = submit_claim(session, _CLAIM, dry_run=True)
        assert result.payload is not None
        assert result.payload["insuredFName"] == "John"

    def test_resolved_ids_present(self):
        session = _mock_session()
        result = submit_claim(session, _CLAIM, dry_run=True)
        assert "csrf_token" in result.resolved_ids
        assert result.resolved_ids["csrf_token"] == "csrf-tok-abc123"


# ── Create mode (default) ────────────────────────────────────────────────────

class TestCreateMode:
    """Default behaviour: create a new claim via claimAdd + claimSave?newFlag=1."""

    def test_gets_claim_add_form(self):
        session = _mock_session()
        submit_claim(session, _CLAIM, dry_run=True)
        get_urls = [call.args[0] for call in session.get.call_args_list]
        assert CLAIM_FORM_URL in get_urls

    def test_posts_to_create_url(self):
        session = _mock_session()
        submit_claim(session, _CLAIM)
        posted_url = session.post.call_args[0][0]
        assert posted_url == CLAIM_SAVE_URL

    def test_claim_file_id_is_auto(self):
        session = _mock_session()
        result = submit_claim(session, _CLAIM, dry_run=True)
        assert result.payload["claimFileID"] == "##AUTO"
        assert result.payload["prefixID"] == "##AUTO"

    def test_parses_claim_id_from_response(self):
        session = _mock_session(post_html="<!-- claimID = [1234567] -->")
        result = submit_claim(session, _CLAIM)
        assert result.claim_id == "claimID=1234567"


# ── Update mode (existing_claim_id) ──────────────────────────────────────────

class TestUpdateMode:
    """existing_claim_id triggers edit-page fetch and newFlag=0 POST."""

    def test_gets_edit_page_with_claim_id(self):
        session = _mock_session()
        submit_claim(session, _CLAIM, dry_run=True, existing_claim_id="8888888")
        edit_calls = [
            c for c in session.get.call_args_list
            if c.args[0] == CLAIM_EDIT_URL
        ]
        assert len(edit_calls) == 1
        assert edit_calls[0].kwargs["params"] == {"claimID": "8888888"}

    def test_does_not_get_claim_add_form(self):
        session = _mock_session()
        submit_claim(session, _CLAIM, dry_run=True, existing_claim_id="8888888")
        get_urls = [call.args[0] for call in session.get.call_args_list]
        assert CLAIM_FORM_URL not in get_urls

    def test_posts_to_update_url(self):
        session = _mock_session(post_html="<html>ok</html>")
        submit_claim(session, _CLAIM, existing_claim_id="8888888")
        posted_url = session.post.call_args[0][0]
        assert posted_url == CLAIM_UPDATE_URL

    def test_claim_file_id_is_existing_id(self):
        session = _mock_session()
        result = submit_claim(session, _CLAIM, dry_run=True, existing_claim_id="8888888")
        assert result.payload["claimFileID"] == "8888888"
        assert result.payload["prefixID"] == ""

    def test_returns_updated_claim_id(self):
        session = _mock_session(post_html="<html>ok</html>")
        result = submit_claim(session, _CLAIM, existing_claim_id="8888888")
        assert result.claim_id == "updated claimID=8888888"

    def test_raises_on_alert_error(self):
        error_html = """<script>alert('Please select a valid company')</script>"""
        session = _mock_session(post_html=error_html)
        with pytest.raises(RuntimeError, match="Claim update failed"):
            submit_claim(session, _CLAIM, existing_claim_id="8888888")


# ── Test mode ─────────────────────────────────────────────────────────────────

class TestTestMode:
    """test_mode=True must override company/contact/email and suppress notifications."""

    def test_overrides_adjuster_and_branch(self):
        session = _mock_session()
        result = submit_claim(
            session, _CLAIM, dry_run=True, test_mode=True,
            test_adjuster_id="111", test_branch_id="222",
        )
        assert result.payload["ACuserID"] == "111"
        assert result.payload["ABID"] == "222"

    def test_overrides_company_id(self):
        session = _mock_session()
        result = submit_claim(
            session, _CLAIM, dry_run=True, test_mode=True,
            test_company_id="143898",
        )
        assert result.payload["companyID"] == "143898"

    def test_clears_contact_and_email(self):
        session = _mock_session()
        result = submit_claim(session, _CLAIM, dry_run=True, test_mode=True)
        assert result.payload["companyUserID"] == "0"
        assert result.payload["companyEMail"] == ""

    def test_suppresses_email_letter(self):
        session = _mock_session()
        result = submit_claim(session, _CLAIM, dry_run=True, test_mode=True)
        assert result.payload["chkEMailLetter"] == "0"
        assert result.payload["chkPDFLetter"] == "0"

    def test_letters_enabled_without_test_mode(self):
        session = _mock_session()
        result = submit_claim(session, _CLAIM, dry_run=True, test_mode=False)
        assert result.payload["chkEMailLetter"] == "1"
        assert result.payload["chkPDFLetter"] == "1"

    def test_resolved_ids_reflect_overrides(self):
        session = _mock_session()
        result = submit_claim(
            session, _CLAIM, dry_run=True, test_mode=True,
            test_adjuster_id="111", test_branch_id="222", test_company_id="333",
        )
        assert result.resolved_ids["adjuster_id"] == "111"
        assert result.resolved_ids["branch_id"] == "222"
        assert result.resolved_ids["company_id"] == "333"
        assert result.resolved_ids["contact_id"] == "0"


# ── Combined modes ────────────────────────────────────────────────────────────

class TestCombinedModes:
    """Verify interactions between dry_run, test_mode, and update mode."""

    def test_dry_run_update_no_post(self):
        session = _mock_session()
        result = submit_claim(
            session, _CLAIM, dry_run=True, existing_claim_id="8888888",
        )
        session.post.assert_not_called()
        assert result.claim_id == "DRY_RUN"

    def test_test_mode_plus_update(self):
        session = _mock_session(post_html="<html>ok</html>")
        result = submit_claim(
            session, _CLAIM, test_mode=True, existing_claim_id="8888888",
            test_adjuster_id="111", test_branch_id="222",
        )
        assert result.claim_id == "updated claimID=8888888"
        assert result.payload["companyUserID"] == "0"
        assert result.payload["chkEMailLetter"] == "0"
