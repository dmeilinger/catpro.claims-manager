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
        """Fetch all unread messages and categorize into processable vs. skipped."""
        url = (
            f"{self.GRAPH_BASE}/users/{self._mailbox}/messages"
            f"?$filter=isRead eq false"
            f"&$expand=attachments"
            f"&$select=id,internetMessageId,subject,from,receivedDateTime,body,hasAttachments"
            f"&$top=10"
        )
        resp = self._request("GET", url)
        raw = resp.json().get("value", [])

        messages: list[EmailMessage] = []
        skipped: list[SkippedEmail] = []

        for msg in raw:
            subject = msg.get("subject", "(no subject)")
            sender = msg.get("from", {}).get("emailAddress", {}).get("address", "unknown")
            received_at = msg.get("receivedDateTime", "")
            internet_message_id = msg.get("internetMessageId", "")
            attachments = msg.get("attachments", [])

            # Extract body_text early — needed for all email types including skipped.
            body_text = msg.get("body", {}).get("content", "")
            if msg.get("body", {}).get("contentType") == "html":
                body_text = BeautifulSoup(body_text, "html.parser").get_text(separator="\n")

            if not attachments:
                skipped.append(SkippedEmail(
                    message_id=msg["id"],
                    internet_message_id=internet_message_id,
                    subject=subject,
                    sender=sender,
                    received_at=received_at,
                    reason="no attachments",
                    body_text=body_text,
                ))
                continue

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
                    message_id=msg["id"],
                    internet_message_id=internet_message_id,
                    subject=subject,
                    sender=sender,
                    received_at=received_at,
                    reason=f"no PDF attachments (found: {attachment_summary})",
                    body_text=body_text,
                ))
                continue

            messages.append(EmailMessage(
                message_id=msg["id"],
                internet_message_id=internet_message_id,
                subject=subject,
                sender=sender,
                received_at=received_at,
                body_text=body_text,
                pdfs=pdfs,
            ))

        return messages, skipped

    def _ensure_folder(self, folder_name: str) -> str:
        """Get or create a mail folder. Returns the folder ID."""
        token = self._token or self._get_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # Check if folder exists
        url = (
            f"{self.GRAPH_BASE}/users/{self._mailbox}/mailFolders"
            f"?$filter=displayName eq '{folder_name}'"
        )
        resp = http_requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        folders = resp.json().get("value", [])
        if folders:
            return folders[0]["id"]

        # Create it
        resp = http_requests.post(
            f"{self.GRAPH_BASE}/users/{self._mailbox}/mailFolders",
            headers=headers,
            json={"displayName": folder_name},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def mark_read(self, message_id: str) -> None:
        """Mark as read and move to Processed folder."""
        token = self._token or self._get_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # Mark as read
        url = f"{self.GRAPH_BASE}/users/{self._mailbox}/messages/{message_id}"
        http_requests.patch(
            url, headers=headers, json={"isRead": True}, timeout=10,
        ).raise_for_status()

        # Move to Processed folder
        folder_id = self._ensure_folder("Processed")
        move_url = f"{self.GRAPH_BASE}/users/{self._mailbox}/messages/{message_id}/move"
        http_requests.post(
            move_url, headers=headers, json={"destinationId": folder_id}, timeout=10,
        ).raise_for_status()
