"""Email source abstraction: Protocol + EML file + MS Graph API implementations."""

import base64
import logging
from datetime import datetime, timezone
from typing import NamedTuple, Protocol

import msal
import requests as http_requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)


# ── Shared data types ────────────────────────────────────────────────────────

class EmailMessage(NamedTuple):
    """Normalized email data from any source."""

    message_id: str  # Source-specific ID (Graph message ID or file path)
    internet_message_id: str  # RFC 2822 Message-ID (stable dedup key)
    subject: str
    sender: str
    received_at: str  # ISO 8601
    body_text: str
    pdfs: dict[str, bytes]  # {doc_type_or_filename: pdf_bytes}


class SkippedEmail(NamedTuple):
    """An unread email the poller saw but cannot process."""

    message_id: str           # Graph message ID
    internet_message_id: str  # RFC 2822 stable dedup key
    subject: str
    sender: str
    received_at: str
    reason: str               # human-readable explanation
    body_text: str            # stored for future agent classification


# ── Protocol ─────────────────────────────────────────────────────────────────

class EmailSource(Protocol):
    def fetch_unread(self) -> tuple[list[EmailMessage], list[SkippedEmail]]:
        """Return (processable messages with PDFs, skipped messages with reasons)."""
        ...

    def mark_read(self, message_id: str) -> None:
        """Mark a message as read/processed in the source system."""
        ...


# ── EML file source (for CLI / testing) ──────────────────────────────────────

def _classify_pdf(filename: str) -> str:
    """Map PDF filename to a doc-type key, matching process_claim.parse_eml logic."""
    fname_flat = " ".join(filename.split())
    if "Claim Summary" in fname_flat:
        return "claim_summary"
    if "Loss Notice" in fname_flat:
        return "loss_notice"
    if "Policy Summary" in fname_flat:
        return "policy_summary"
    return fname_flat or "attachment"


class EmlFileSource:
    """Wraps a local .eml file as a single-message EmailSource."""

    def __init__(self, eml_path: str):
        self._path = eml_path
        self._consumed = False

    def fetch_unread(self) -> tuple[list[EmailMessage], list[SkippedEmail]]:
        if self._consumed:
            return [], []
        self._consumed = True

        from app.services.eml_parser import parse_eml

        body, pdfs = parse_eml(self._path)
        return [
            EmailMessage(
                message_id=self._path,
                internet_message_id=f"file://{self._path}",
                subject=self._path,
                sender="local",
                received_at=datetime.now(timezone.utc).isoformat(),
                body_text=body,
                pdfs=pdfs,
            )
        ], []

    def mark_read(self, message_id: str) -> None:
        pass  # No-op for local files


# ── MS Graph API source ─────────────────────────────────────────────────────

class GraphMailSource:
    """Polls an M365 shared mailbox via Graph API (client credentials flow)."""

    GRAPH_BASE = "https://graph.microsoft.com/v1.0"

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        mailbox: str,
    ):
        self._mailbox = mailbox
        self._app = msal.ConfidentialClientApplication(
            client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            client_credential=client_secret,
        )
        self._token: str | None = None

    def _get_token(self) -> str:
        result = self._app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )
        if "access_token" not in result:
            raise RuntimeError(
                f"Graph auth failed: {result.get('error_description', result)}"
            )
        self._token = result["access_token"]
        return self._token

    def _headers(self) -> dict[str, str]:
        token = self._token or self._get_token()
        return {"Authorization": f"Bearer {token}"}

    def _request(self, method: str, url: str, **kwargs) -> http_requests.Response:
        """Make a Graph API request with automatic token refresh on 401."""
        resp = http_requests.request(
            method, url, headers=self._headers(), timeout=30, **kwargs
        )
        if resp.status_code == 401:
            self._token = None
            resp = http_requests.request(
                method, url, headers=self._headers(), timeout=30, **kwargs
            )
        resp.raise_for_status()
        return resp

    def fetch_unread(self) -> tuple[list[EmailMessage], list[SkippedEmail]]:
        """Fetch all unread messages via two-phase fetch with @odata.nextLink pagination.

        Phase 1: GET metadata only — no $expand=attachments (avoids 100MB+ responses).
        Phase 2: GET /messages/{id}/attachments separately, only for hasAttachments=true.
        Pages are followed via @odata.nextLink up to MAX_PAGES safety cap.
        All requests go through self._request() to get automatic 401 token refresh.
        """
        MAX_PAGES = 20  # claims mailbox should never have 1,000 unread

        url: str | None = (
            f"{self.GRAPH_BASE}/users/{self._mailbox}/messages"
            f"?$filter=isRead eq false"
            f"&$select=id,internetMessageId,subject,from,receivedDateTime,body,hasAttachments"
            f"&$top=50"
        )

        messages: list[EmailMessage] = []
        skipped: list[SkippedEmail] = []
        page_count = 0

        while url and page_count < MAX_PAGES:
            page_count += 1
            resp = self._request("GET", url)
            body_data = resp.json()

            for msg in body_data.get("value", []):
                subject = msg.get("subject", "(no subject)")
                sender = msg.get("from", {}).get("emailAddress", {}).get("address", "unknown")
                received_at = msg.get("receivedDateTime", "")
                internet_message_id = msg.get("internetMessageId", "")
                has_attachments = msg.get("hasAttachments", False)
                msg_id = msg["id"]

                # Extract body_text early — needed for all email types including skipped.
                body_text = msg.get("body", {}).get("content", "")
                if msg.get("body", {}).get("contentType") == "html":
                    body_text = BeautifulSoup(body_text, "html.parser").get_text(separator="\n")

                if not has_attachments:
                    skipped.append(SkippedEmail(
                        message_id=msg_id,
                        internet_message_id=internet_message_id,
                        subject=subject,
                        sender=sender,
                        received_at=received_at,
                        reason="no attachments",
                        body_text=body_text,
                    ))
                    continue

                # Phase 2: fetch attachment bytes separately (only for hasAttachments=true)
                att_resp = self._request(
                    "GET",
                    f"{self.GRAPH_BASE}/users/{self._mailbox}/messages/{msg_id}/attachments",
                )
                attachments = att_resp.json().get("value", [])

                pdfs: dict[str, bytes] = {}
                for att in attachments:
                    if att.get("contentType") == "application/pdf" and att.get("contentBytes"):
                        pdf_bytes = base64.b64decode(att["contentBytes"])
                        pdfs[_classify_pdf(att.get("name", "attachment.pdf"))] = pdf_bytes

                if not pdfs:
                    attachment_summary = ", ".join(
                        f"{att.get('name', '?')} ({att.get('contentType', '?')})"
                        for att in attachments
                    )
                    skipped.append(SkippedEmail(
                        message_id=msg_id,
                        internet_message_id=internet_message_id,
                        subject=subject,
                        sender=sender,
                        received_at=received_at,
                        reason=f"no PDF attachments (found: {attachment_summary})",
                        body_text=body_text,
                    ))
                    continue

                messages.append(EmailMessage(
                    message_id=msg_id,
                    internet_message_id=internet_message_id,
                    subject=subject,
                    sender=sender,
                    received_at=received_at,
                    body_text=body_text,
                    pdfs=pdfs,
                ))

            # IMPORTANT: follow nextLink via self._request() — never raw http — so
            # 401 token refresh applies to all pages, not just page 1.
            url = body_data.get("@odata.nextLink")

        log.info(
            "Fetched %d message(s), %d skipped across %d page(s)",
            len(messages), len(skipped), page_count,
        )
        return messages, skipped

    def _ensure_folder(self, folder_name: str) -> str:
        """Get or create a mail folder. Returns the folder ID.

        folder_name must be a trusted internal value ('Processed') — never user input.
        """
        # Check if folder exists
        url = (
            f"{self.GRAPH_BASE}/users/{self._mailbox}/mailFolders"
            f"?$filter=displayName eq '{folder_name}'"
        )
        resp = self._request("GET", url)
        folders = resp.json().get("value", [])
        if folders:
            return folders[0]["id"]

        # Create it
        resp = self._request(
            "POST",
            f"{self.GRAPH_BASE}/users/{self._mailbox}/mailFolders",
            json={"displayName": folder_name},
        )
        return resp.json()["id"]

    def mark_read(self, message_id: str) -> None:
        """Mark as read and move to Processed folder."""
        # Mark as read
        url = f"{self.GRAPH_BASE}/users/{self._mailbox}/messages/{message_id}"
        self._request("PATCH", url, json={"isRead": True})

        # Move to Processed folder
        folder_id = self._ensure_folder("Processed")
        move_url = f"{self.GRAPH_BASE}/users/{self._mailbox}/messages/{message_id}/move"
        self._request("POST", move_url, json={"destinationId": folder_id})
