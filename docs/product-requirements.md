# Product Requirements: FileTrac Claim Automation

## Business Context

CatPro Insurance Services, LLC is a catastrophe claims adjusting firm. When an insurance carrier assigns a new claim to CatPro, they send an email with PDF attachments (Claim Summary, Loss Notice, Policy Summary). A CatPro staff member must then manually re-enter all of that information into FileTrac — CatPro's claims management system — before an adjuster can be dispatched.

This manual re-entry is time-consuming, error-prone, and scales poorly during high-volume CAT events when dozens of claims arrive at once.

## Goal

Eliminate manual claim entry. When a carrier sends a claim assignment email, the system should automatically read it and create the corresponding claim in FileTrac — with no human data entry required.

## Users

- **Primary beneficiary**: CatPro office staff who currently key in claim data manually
- **Indirect beneficiary**: Adjusters who get their assignments faster; carriers who get faster acknowledgement

## Functional Requirements

### FR-1: Email Ingestion
The system must accept inbound claim assignment emails. Initially via local `.eml` file; subsequently via Microsoft 365 shared mailbox watch.

### FR-2: Data Extraction
The system must extract all required claim fields from the email body and PDF attachments:
- Insured name, address, phone, email
- Secondary insured (if present)
- Policy number, effective/expiration dates, policy type
- Date of loss, type of loss, loss description
- Loss location address
- Client claim number (carrier's reference number)
- Insurer/carrier name
- Assigned adjuster name
- Agent/agency contact information

### FR-3: FileTrac Claim Creation
The system must create a new claim record in FileTrac (cms14.filetrac.net) with all extracted fields populated, without any browser or human interaction at runtime.

### FR-4: Adjuster Assignment
The system must resolve the adjuster name from the email to a FileTrac user ID and assign the claim accordingly.

### FR-5: Fully Automatic
No human approval step between email receipt and claim creation. The system acts immediately on receipt.

### FR-6: Acknowledgement Letter
FileTrac should send the standard acknowledgement letter to the carrier contact on claim creation (handled by FileTrac natively via the `chkEMailLetter` flag).

## Non-Functional Requirements

### NFR-1: Reliability
The system must handle auth failures, malformed emails, and missing fields gracefully — logging errors without crashing. A failed claim should surface to staff for manual handling, not silently disappear.

### NFR-2: Security
- Credentials (email, password, TOTP secret) stored only in `.env` — never logged or committed to version control
- No credentials passed as command-line arguments

### NFR-3: Speed
End-to-end processing (email receipt → FileTrac claim created) should complete within 60 seconds under normal conditions.

### NFR-4: Carrier Coverage
Initial release supports **Acuity Insurance** PDF format only. Architecture should make it straightforward to add new carriers (new PDF parser per carrier, or LLM-based fallback).

## Scope

### In Scope (Phase 1 — Complete)
- Parse `.eml` files with Acuity Insurance PDF attachments
- Deterministic PDF extraction (no LLM required for Acuity format)
- FileTrac HTTP automation: Cognito auth, SSO bridge, claim form submission
- Adjuster name → ID lookup via local `adjusters.json`

### In Scope (Phase 2 — Next)
- Microsoft 365 shared mailbox integration (watch for new claim emails automatically)
- Trigger `process_claim.py` on new email arrival without manual file handling

### Out of Scope (Future)
- Support for carriers other than Acuity (architecture allows it; not yet implemented)
- FileTrac claim status updates / adjuster field reports
- Two-way sync between FileTrac and carrier portals
- Mobile notifications

## Success Criteria

- A claim assignment email received in the monitored mailbox results in a correctly populated FileTrac claim record within 60 seconds, with no manual intervention
- Zero data entry errors attributable to the automation (vs. human keying errors)
- Staff time saved: ~5–10 minutes per claim during normal operations; significantly more during CAT surge events
