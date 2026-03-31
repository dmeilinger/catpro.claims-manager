# Architecture: FileTrac Claim Automation

## Overview

A Python pipeline that ingests claim assignment emails, extracts structured data from PDF attachments, and submits the claim to FileTrac via HTTP — no browser, no manual steps.

```
Email (EML / M365 mailbox)
    │
    ▼
parse_eml()          — MIME parse: extract body text + PDF attachments
    │
    ▼
extract_claim_fields() — Deterministic PDF parsing (Acuity format) via pdfplumber
    │
    ▼
login(session)       — AWS Cognito SRP + TOTP → evolveLogin SSO → ASPSESSIONID cookie
    │
    ▼
submit_claim()       — Dynamic ID resolution + POST to claimSave.asp
    │
    ▼
FileTrac claim record created  →  claimID=NNNNNNN
```

## Runtime Environment

- **Language**: Python 3.13 (system `python3` is 3.9 — always invoke as `python3.13`)
- **Dependencies**: see `requirements.txt`
- **Config**: `.env` file in project root (never committed)

## Module: `process_claim.py`

Single-file implementation. All phases are importable functions.

### Phase 1 — EML Parsing (`parse_eml`)

Uses stdlib `email` module. Walks MIME parts, classifies PDFs by filename substring:

| Filename contains | Key |
|-------------------|-----|
| `"Claim Summary"` | `claim_summary` |
| `"Loss Notice"` | `loss_notice` |
| `"Policy Summary"` | `policy_summary` |

Filename whitespace is normalized (some mail clients wrap long attachment names).

### Phase 2 — PDF Extraction (`extract_claim_fields`)

**Acuity Insurance only** — deterministic regex, no LLM.

`pdfplumber` extracts raw text. Acuity uses a two-column PDF layout; pdfplumber merges columns onto the same line, so regexes use `(?:[^\n]*\n)*?` to skip injected right-column content.

| PDF | Fields extracted |
|-----|-----------------|
| Claim Summary | Insured name/address/phone, secondary insured, policy #, loss date, loss location, agency block, client claim # |
| Loss Notice | Loss description, loss address (authoritative), date of loss |
| Policy Summary | Policy effective date, policy expiration date |
| Email body | Assigned adjuster name (salutation) |

To add a new carrier: implement `_parse_<carrier>_*` functions and dispatch by `client_company_name`. Alternatively, add an LLM-based fallback in `extract_claim_fields` for unrecognized formats.

**`ClaimData`** is a Pydantic model — all fields `str | None = None`.

### Phase 3 — Authentication (`login`)

Three-step flow — all HTTP, no browser at runtime:

1. **AWS Cognito SRP** via `pycognito`:
   - `InitiateAuth (USER_SRP_AUTH)` → `PASSWORD_VERIFIER` challenge
   - `RespondToAuthChallenge (PASSWORD_VERIFIER)` → `SOFTWARE_TOKEN_MFA` challenge
   - `RespondToAuthChallenge (SOFTWARE_TOKEN_MFA + TOTP)` → `AuthenticationResult`
   - Pool: `us-east-1_BOlb3igmv`, Client ID: `1frtspmi2af7o8hqtfsfebrc6`

2. **TOTP** via `pyotp`:
   - Secret from `FILETRAC_TOTP_SECRET` env var
   - Window-boundary guard: waits if < 5s remaining in current 30s window
   - ⚠️ Two logins within the same window cause `ExpiredCodeException` — don't run back-to-back

3. **evolveLogin SSO bridge**:
   - `POST https://cms14.filetrac.net/system/evolveLogin.asp`
   - Fields: `userId=305873` (CatPro legacy ID), `evolveUserId=<Cognito sub>`, `access_token=<Cognito access token>`, `URL=claimList.asp`
   - Sets `ASPSESSIONID*` cookie valid for all cms14.filetrac.net requests

### Phase 4 — Claim Submission (`submit_claim`)

**Step 1**: `GET https://cms14.filetrac.net/system/claimAdd.asp`
- Extracts `pageLayout_CSRtoken` (fresh GUID, required in every POST)
- Extracts `ACmgrID` options (manager select)

**Step 2**: Dynamic ID resolution via `claimEdit_clientList.asp`:

| Mode | Endpoint | Returns |
|------|----------|---------|
| `customerCompanies` | `?mode=customerCompanies&tgtCompany=<name>` | `companyID` from `<rs id='NNN'>` |
| `customerReps` | `?mode=customerReps&companyID=<id>` | `companyUserID` (first contact entry after header) + `companyEMail` (from header) |
| `customerBranches` | `?mode=customerBranches&companyID=<id>` | `ABID` from first `NNN##Branch Name` |

`customerReps` response format:
```
##/##CompanyName##email@example.com##...##342436##319972##...##~342636####Rep, Bob##...
```
- Entry 0 (before `~`): company header — field 3 is company email, field 6 is a system ID
- Entries 1+ (after `~`): contacts — field 0 is `companyUserID`

**Step 3**: `POST https://cms14.filetrac.net/system/claimSave.asp?newFlag=1&anotherFlag=0`
- ~80 form fields (see `submit_claim` in `process_claim.py` for complete payload)
- Key non-obvious fields: `companyUserEMail=-1`, `companyUserEmail_display=NONE`, `ContactLineCount=1`, `letterText=<acknowledgement text>`, `claimFileID2=`

**Step 4**: Success detection
- Response body contains `<!-- claimID = [NNNNNNN] -->` on success
- Returns `"claimID=NNNNNNN"`

### Adjuster Resolution (`resolve_adjuster_id`)

`adjusters.json` maps `"Last, First"` → FileTrac user ID (scraped from dropdown). Word-level case-insensitive matching handles first-name-only inputs from email salutations. Fallback: `302465` (UNASSIGNED).

### ACmgrID Resolution (`_parse_select_first_value`)

Parses `ACmgrID` select from `claimAdd.asp` HTML. Skips placeholder values: `-1`, `0`, `302465`, options containing "Select", "UNASSIGNED", or `---`. For CatPro, expected result is `319972`.

## Key Constants (CatPro-specific)

| Constant | Value | Description |
|----------|-------|-------------|
| `FILETRAC_LEGACY_USER_ID` | `305873` | CatPro's FileTrac user ID for SSO bridge |
| `COGNITO_USER_POOL_ID` | `us-east-1_BOlb3igmv` | FTEvolve Cognito pool |
| `COGNITO_CLIENT_ID` | `1frtspmi2af7o8hqtfsfebrc6` | FTEvolve Cognito app client |
| UNASSIGNED adjuster | `302465` | FileTrac ID for UNASSIGNED (not `0`) |

## Phase 2: MS O365 Integration (Planned)

Replace manual `.eml` file input with automatic mailbox watching:

- **Trigger**: New email in shared claims mailbox (e.g. `claims@catpro.us.com`)
- **API**: Microsoft Graph API — either webhook subscriptions or polling
- **MCP tools available**: `mcp__claude_ai_Microsoft_365__*` (configured globally)
- **Integration point**: Retrieve email + attachments → pass to existing `parse_eml` / `extract_claim_fields` / `submit_claim` pipeline unchanged

## Security

- All credentials in `.env` (gitignored): `FILETRAC_EMAIL`, `FILETRAC_PASSWORD`, `FILETRAC_TOTP_SECRET`
- No credentials in logs, stdout, or committed files
- `adjusters.json` contains no credentials — safe to commit

## File Structure

```
process_claim.py          — Main pipeline (all phases)
adjusters.json            — Adjuster name → FileTrac ID mapping
requirements.txt          — Python dependencies
.env                      — Credentials (gitignored)
docs/
  product-requirements.md — Business context and requirements
  architecture.md         — This document
  brainstorms/            — Early design notes (historical)
  plans/                  — Implementation plans (historical)
```
