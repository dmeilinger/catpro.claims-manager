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

from app.config import get_settings
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

    cfg = get_settings()

    print("[3/4] Authenticating to FileTrac...")
    session = build_session()
    login(session)
    print("      Authenticated.")

    mode_parts = []
    if cfg.dry_run:
        mode_parts.append("DRY RUN")
    if cfg.test_mode:
        mode_parts.append("TEST MODE")
    if cfg.filetrac_test_claim_id:
        mode_parts.append(f"UPDATE claimID={cfg.filetrac_test_claim_id}")
    mode_label = " | ".join(mode_parts) if mode_parts else "LIVE"
    print(f"[4/4] Submitting claim [{mode_label}]...")

    result = submit_claim(
        session,
        claim,
        dry_run=cfg.dry_run,
        test_mode=cfg.test_mode,
        test_adjuster_id=cfg.test_adjuster_id,
        test_branch_id=cfg.test_branch_id,
        test_company_id=cfg.test_company_id,
        existing_claim_id=cfg.filetrac_test_claim_id,
    )
    print(f"      Result: {result.claim_id}")
