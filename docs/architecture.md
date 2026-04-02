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

## Phase 2: MS O365 Email Polling

Automatic mailbox polling replaces manual `.eml` file input.

### Architecture

```
GraphMailSource (email_source.py)
    │  MS Graph API — client credentials flow (msal)
    │  GET /users/{mailbox}/messages?$filter=isRead eq false
    │  $expand=attachments (inline base64 PDF bytes)
    ▼
EmailMessage(NamedTuple)
    │  Normalized: message_id, internet_message_id, subject,
    │              sender, received_at, body_text, pdfs dict
    ▼
Poller (poller.py)
    │  while True: poll_once() → sleep(interval)
    │  Dedup via ClaimDatabase.is_duplicate()
    │  Reuses single FileTrac session per cycle
    ▼
extract_claim_fields()  →  login()  →  submit_claim()
    │  (unchanged from Phase 1)
    ▼
ClaimDatabase (db.py)
    │  SQLite — insert_pending → mark_success(claim_id) / mark_error
    ▼
claims.db
```

### Email Source Abstraction (`email_source.py`)

`EmailSource` is a `typing.Protocol` with two methods:
- `fetch_unread() -> list[EmailMessage]` — return unread messages with PDFs
- `mark_read(message_id: str) -> None` — mark as read and move to "Processed" folder

Implementations:
| Class | Use case |
|-------|----------|
| `EmlFileSource` | CLI / testing — wraps existing `parse_eml()` |
| `GraphMailSource` | Production — polls M365 shared mailbox via Graph API |

This enables future webhook triggers: a webhook handler constructs `EmailMessage` directly and calls `_process_message()` — no new source class needed.

### Graph API Authentication

CatPro is a separate M365 tenant. Uses `msal.ConfidentialClientApplication` with client credentials flow (application permissions, no user interaction).

**Azure AD prerequisites** (manual setup in CatPro tenant):
1. Register application → tenant ID + client ID
2. Add API permissions: `Mail.Read`, `Mail.ReadWrite`, `Mail.Send` (Application type)
3. Grant admin consent (via `az rest` app role assignments)
4. Create client secret → store in `.env`
5. (Recommended) Application access policy to restrict to shared mailbox only

### SQLite Tracking (`db.py`)

Two tables: `processed_emails` tracks email processing status, `claim_data` captures all extracted fields and the submission payload.

```sql
CREATE TABLE processed_emails (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id          TEXT NOT NULL,      -- Graph API message ID (for API calls)
    internet_message_id TEXT NOT NULL,      -- RFC 2822 Message-ID (dedup key)
    subject             TEXT,
    sender              TEXT,
    received_at         TEXT,
    processed_at        TEXT NOT NULL,
    claim_id            TEXT,              -- FileTrac claim ID (e.g. "claimID=1234567") or "DRY_RUN"
    status              TEXT NOT NULL,     -- pending | success | error
    error_message       TEXT,
    UNIQUE(internet_message_id)
);

CREATE TABLE claim_data (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id                INTEGER NOT NULL REFERENCES processed_emails(id),
    -- All extracted fields from PDF/email parsing (mirrors ClaimData model)
    insured_first_name      TEXT,
    insured_last_name       TEXT,
    ...                     -- 30 fields total (insured, loss, client, agent, policy)
    -- Resolved FileTrac IDs
    filetrac_company_id     TEXT,
    filetrac_contact_id     TEXT,
    filetrac_branch_id      TEXT,
    filetrac_adjuster_id    TEXT,
    filetrac_manager_id     TEXT,
    filetrac_csrf_token     TEXT,
    -- Full submission payload as JSON (~80 form fields)
    submission_payload      TEXT,
    created_at              TEXT NOT NULL
);
```

Crash-safe: `processed_emails` row inserted as `pending` before processing, updated to `success`/`error` after. `claim_data` row inserted on success with all extracted fields and the exact payload that would be (or was) POSTed to FileTrac.

### Configuration (`config.py`)

Pydantic `Settings` class loads all config from `.env`:

```
# Azure AD (CatPro tenant)
AZURE_TENANT_ID=<guid>
AZURE_CLIENT_ID=<guid>
AZURE_CLIENT_SECRET=<secret>
M365_MAILBOX=claims-test@catpro.us.com

# Polling
POLL_INTERVAL_SECONDS=60
DB_PATH=data/claims.db

# Dry run — skips billable POST, saves everything else to DB
DRY_RUN=true
```

### Entry Points

```bash
python3.13 -m catpro.poller              # poll mailbox
python3.13 -m catpro.process_claim email.eml  # process single EML file
```

Handles SIGTERM/SIGINT for clean Docker shutdown (1-second interruptible sleep).

### Post-Processing

- **Success**: email marked read and moved to **"Processed"** folder (auto-created)
- **Failure**: email left unread in inbox for manual review; error recorded in DB

### Error Handling

- **Session expiry**: re-authenticates to FileTrac with one retry
- **Graph API token refresh**: automatic on 401
- **TOTP safety**: single FileTrac session reused across all messages in a poll cycle
- **mark_read failure**: logged as warning, does not affect claim success status

### DRY_RUN Mode

`DRY_RUN=true` runs the full pipeline (poll, parse, extract, authenticate, resolve IDs, build payload) but skips the final `POST claimSave.asp`. No billable claim is created in FileTrac. All data is still saved to `claim_data` — useful for validating the entire pipeline without cost.

### Test Email Generator (`test_email.py`)

Sends real emails to the test mailbox via Graph API `sendMail` (from the FileTrac user account). Uses mock Acuity PDFs from `data/templates/sample_acuity_claim.eml` — all fictional data, no real PII.

```bash
python3.13 -m catpro.test_email --ref 0001 --adjuster "Doug"
```

## Phase 3: FastAPI Deployment (Planned)

Future deployment as a Docker container with FastAPI:

- `Poller.poll_once()` wrapped in `asyncio.to_thread` as a background task
- `POST /webhook` endpoint for MS Graph change notifications (replaces polling)
- `GET /history` endpoint backed by `ClaimDatabase.get_history()`
- `GET /health` endpoint
- SQLite DB on a Docker volume (not ephemeral container filesystem)
- Deployed via `uvicorn` in a `Dockerfile`

## Security

- All credentials in `.env` (gitignored): `FILETRAC_EMAIL`, `FILETRAC_PASSWORD`, `FILETRAC_TOTP_SECRET`, `AZURE_*`
- No credentials in logs, stdout, or committed files
- `adjusters.json` contains no credentials — safe to commit
- Azure AD app should be scoped to shared mailbox only via application access policy

## File Structure

```
catpro/                     — Main Python package
  __init__.py
  process_claim.py          — Core pipeline: parse, extract, auth, submit (Phase 1)
  email_source.py           — Email source abstraction: Protocol + EML + Graph API
  db.py                     — SQLite tracking: processed_emails + claim_data tables
  config.py                 — Pydantic settings from .env
  poller.py                 — Polling loop + orchestration (Phase 2 entry point)
  test_email.py             — Inject test emails into M365 mailbox
  adjusters.json            — Adjuster name → FileTrac ID mapping
data/                       — Runtime data (gitignored except .gitkeep)
  claims.db                 — SQLite database (created at runtime)
  templates/
    sample_acuity_claim.eml — Mock Acuity claim with fake data (for testing)
requirements.txt            — Python dependencies
.env                        — Credentials (gitignored)
docs/
  product-requirements.md   — Business context and requirements
  architecture.md           — This document
  brainstorms/              — Early design notes (historical)
  plans/                    — Implementation plans (historical)
```
