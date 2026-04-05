#!/usr/bin/env python3
"""
claim_processor.py — FileTrac claim automation orchestrator.

Thin module that re-exports all public symbols from the four service modules
and provides the CLI entry point (main). Import from here for backward
compatibility, or import directly from the specific module.

  eml_parser      — parse_eml
  pdf_extractor   — ClaimData, extract_claim_fields
  filetrac_auth   — build_session, login
  filetrac_submit — submit_claim, SubmitResult
"""

import sys

from dotenv import load_dotenv

from app.services.eml_parser import parse_eml
from app.services.filetrac_auth import build_session, login
from app.services.filetrac_submit import SubmitResult, submit_claim
from app.services.pdf_extractor import ClaimData, extract_claim_fields

load_dotenv()

__all__ = [
    "parse_eml",
    "ClaimData",
    "extract_claim_fields",
    "build_session",
    "login",
    "SubmitResult",
    "submit_claim",
]


# ── Phase 5: Main ─────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python3 process_claim.py <path/to/email.eml>", file=sys.stderr)
        sys.exit(1)

    eml_path = sys.argv[1]

    print(f"[1/4] Parsing {eml_path}...")
    email_body, pdfs = parse_eml(eml_path)
    print(f"      Found {len(pdfs)} PDF(s): {list(pdfs.keys())}")

    print("[2/4] Extracting claim fields via Claude API...")
    claim = extract_claim_fields(email_body, pdfs)
    print(f"      Insured:  {claim.insured_first_name} {claim.insured_last_name}")
    print(f"      Policy:   {claim.policy_number}")
    print(f"      Loss:     {claim.loss_date} — {claim.loss_type}")
    print(f"      Client #: {claim.client_claim_number}")
    print(f"      Adjuster: {claim.assigned_adjuster_name}")

    print("[3/4] Authenticating to FileTrac...")
    session = build_session()
    login(session)
    print("      Authenticated.")

    print("[4/4] Submitting claim...")
    result = submit_claim(session, claim)
    print(f"      Claim created: {result.claim_id}")
