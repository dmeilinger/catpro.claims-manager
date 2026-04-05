#!/usr/bin/env python3
"""
test_email.py — Inject test claim emails into the M365 test mailbox.

Uses Graph API to create messages directly in the inbox (no Mail.Send needed,
Mail.ReadWrite is sufficient). Extracts PDFs from an existing EML file and
attaches them to a new message marked as unread.

Usage:
    python3.13 -m catpro.test_email                        # uses default EML
    python3.13 -m catpro.test_email path/to/other.eml      # use different EML
    python3.13 -m catpro.test_email --adjuster "Alan"       # override adjuster name
"""

import argparse
import base64
import email.mime.application
import email.mime.multipart
import email.mime.text
import logging
import sys
from email.utils import formatdate

import requests as http_requests

from app.config import get_settings
from app.services.email_source import GraphMailSource
from app.services.eml_parser import parse_eml

log = logging.getLogger(__name__)

# Filename templates matching Acuity's naming convention
PDF_FILENAMES = {
    "claim_summary": "Claim Summary - TG{ref}.pdf",
    "loss_notice": "Loss Notice - TG{ref}.pdf",
    "policy_summary": "Policy Summary - TG{ref}.pdf",
}

DEFAULT_BODY = """{adjuster},

This is a test claim assignment.

Thanks,
CW

________________________________
From: Sarah Callaway <scallaway@test-carrier.example.com>
Sent: Monday, March 30, 2026 6:17 PM
To: Claims <claims@catpro.us.com>
Subject: TG{ref}

Dear CatPro Insurance Services:

Please find attached a new assignment. Please send your acknowledgement
and adjuster information to us at claims@test-carrier.example.com.

Claim Number: TG{ref}

Thank you,
Sarah Callaway
Test Carrier Insurance
"""


def inject_test_email(
    eml_path: str = "data/templates/sample_acuity_claim.eml",
    adjuster: str = "Alan",
    ref: str = "9999",
    subject: str | None = None,
    sender: str = "scallaway@test-carrier.example.com",
) -> str:
    """Send a test email to the test mailbox. Returns 'sent'."""
    settings = get_settings()

    # Extract PDFs from source EML
    _, pdfs = parse_eml(eml_path)
    if not pdfs:
        raise RuntimeError(f"No PDFs found in {eml_path}")

    subject = subject or f"TG{ref}"
    body_text = DEFAULT_BODY.format(adjuster=adjuster, ref=ref)

    # Build attachments
    attachments = []
    for doc_type, pdf_bytes in pdfs.items():
        filename = PDF_FILENAMES.get(doc_type, f"{doc_type}.pdf").format(ref=ref)
        attachments.append({
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": filename,
            "contentType": "application/pdf",
            "contentBytes": base64.b64encode(pdf_bytes).decode(),
        })

    # Authenticate
    source = GraphMailSource(
        tenant_id=settings.azure_tenant_id,
        client_id=settings.azure_client_id,
        client_secret=settings.azure_client_secret.get_secret_value(),
        mailbox=settings.m365_mailbox,
    )
    token = source._get_token()

    # Send from a licensed user to the shared mailbox. Shared mailboxes
    # can't send directly via Graph API, so we send from the FileTrac user.
    send_as = settings.filetrac_email
    url = f"https://graph.microsoft.com/v1.0/users/{send_as}/sendMail"
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "text", "content": body_text},
            "replyTo": [{"emailAddress": {"address": sender, "name": "Sarah Callaway"}}],
            "toRecipients": [
                {"emailAddress": {"address": settings.m365_mailbox}},
            ],
            "attachments": attachments,
        },
        "saveToSentItems": False,
    }

    resp = http_requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    return "sent"


def main() -> None:
    parser = argparse.ArgumentParser(description="Inject test claim email into M365 mailbox")
    parser.add_argument("eml", nargs="?", default="data/templates/sample_acuity_claim.eml", help="Source EML file for PDF attachments")
    parser.add_argument("--adjuster", default="Alan", help="Adjuster name in email salutation (default: Alan)")
    parser.add_argument("--ref", default="9999", help="Claim reference number (default: 9999)")
    parser.add_argument("--subject", default=None, help="Email subject (default: TG<ref>)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    settings = get_settings()
    print(f"Target mailbox: {settings.m365_mailbox}")
    print(f"Source EML:     {args.eml}")
    print(f"Adjuster:       {args.adjuster}")
    print(f"Ref:            TG{args.ref}")

    inject_test_email(
        eml_path=args.eml,
        adjuster=args.adjuster,
        ref=args.ref,
        subject=args.subject,
    )
    print("Email sent — should arrive in inbox shortly.")


if __name__ == "__main__":
    main()
