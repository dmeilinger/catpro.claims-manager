---
date: 2026-03-30
topic: filetrac-claim-automation
---

# FileTrac Claim Automation

## What We're Building

A Python script that reads an `.eml` file (claim assignment email from an insurance carrier),
extracts claim data from the email body and PDF attachments using Claude API, then automatically
creates the claim in FileTrac via HTTP — no browser, no manual data entry.

First target: `Fw_ TG4832.eml` from Acuity Insurance.

## Why This Approach

Started with full webhook architecture (M365 → Azure Function → Claude → FileTrac) but chose
to build the core file-based version first. Webhooks are just a trigger — getting the extraction
and submission logic right is the hard part. File reader is faster to iterate on locally.

## Key Decisions

- **Input**: `.eml` file (MIME-parsed to extract body + PDF attachments)
- **Extraction**: Claude API reads PDFs + email body, returns structured JSON claim fields
- **Submission**: Python `requests` — HTTP POST to FileTrac (no browser needed)
- **Auth**: Session cookie via login + TOTP (`pyotp`), then CSRF token from `claimAdd.asp`
- **Human approval**: None — fully automatic end to end
- **Email provider**: M365 / Office 365 (webhook integration deferred to later)

## Architecture

```
.eml file
    ↓  parse MIME (email stdlib)
email body + PDF attachments
    ↓  Claude API (claude-opus-4-6 or sonnet-4-6)
structured claim JSON
    ↓  FileTrac HTTP client
  1. POST login → session cookie
  2. TOTP → MFA → authenticated session
  3. GET claimAdd.asp → extract CSRF token
  4. POST claim form fields
Claim created in FileTrac ✓
```

## FileTrac Key Details

- **Login URL**: `https://ftevolve.com/auth/login`
- **MFA URL**: `https://ftevolve.com/auth/mfa` (needs exact endpoint — intercept during build)
- **Claim form**: `https://cms14.filetrac.net/system/claimAdd.asp`
- **CSRF field**: `pageLayout_CSRtoken` (fresh GUID per page load)
- **Session**: Cookie-based (classic ASP)
- **Credentials**: `.env` file

## Field Mapping (PDF → FileTrac)

| Source | FileTrac Field | Form Name |
|--------|---------------|-----------|
| Claim Summary PDF | Client Claim # | `companyFileID` |
| Claim Summary PDF | Insured First Name | `insuredFName` |
| Claim Summary PDF | Insured Last Name | `insuredLName` |
| Claim Summary PDF | Insured Email | `insuredEMail` |
| Claim Summary PDF | Insured Phone | `insuredPhone` |
| Claim Summary PDF | Insured Cell | `insuredPhone3` |
| Claim Summary PDF | Insured Address | `insuredAddr1` |
| Claim Summary PDF | Insured City/State/ZIP | `insuredCity/State/ZIP` |
| Claim Summary PDF | Policy # | `insuredPolicyNum` |
| Claim Summary PDF | Secondary Insured First | `secondaryInsuredFName` |
| Claim Summary PDF | Secondary Insured Last | `secondaryInsuredLName` |
| Claim Summary PDF | Loss Address | `lossAddr1/City/State/ZIP` |
| Loss Notice PDF | Date of Loss | `lossDate` |
| Loss Notice PDF | Type of Loss | `lossType` |
| Loss Notice PDF | Loss Description | textarea |
| Email body | Assigned Adjuster (name) | `ACuserID` (lookup from dropdown) |
| Auto | Date Received | `claimDateReceived` (today) |
| Auto | Client Company | `companyIDTxt` (Acuity Insurance) |

## Open Questions

- Exact MFA POST endpoint and payload (need to intercept)
- How `companyIDTxt` autocomplete works server-side (may need a lookup request first)
- Whether `stormID` dropdown needs to be set for storm claims
- Adjuster name → ID mapping (dropdown has IDs, email has names)

## Next Steps

→ `/ce:plan` for implementation details
→ Then intercept auth flow to confirm exact endpoints
→ Test against FileTrac with a real `.eml` file (use staging mindset — verify before first live run)
