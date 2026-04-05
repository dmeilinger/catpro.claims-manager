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

Automatic mailbox polling via MS Graph API. The poller runs as a managed subprocess under the FastAPI backend (see Phase 3).

### Email Source Abstraction (`backend/app/services/email_source.py`)

`EmailSource` is a `typing.Protocol`:

```python
def fetch_unread() -> tuple[list[EmailMessage], list[SkippedEmail]]: ...
def mark_read(message_id: str) -> None: ...
```

**`EmailMessage`** (NamedTuple) — an email with PDF attachments, ready for claim processing:
- `message_id` — Graph API message ID (used for API calls like mark_read)
- `internet_message_id` — RFC 2822 Message-ID (stable dedup key)
- `subject`, `sender`, `received_at`, `body_text`
- `pdfs` — `dict[str, bytes]` keyed by doc type (`claim_summary`, `loss_notice`, `policy_summary`)

**`SkippedEmail`** (NamedTuple) — an unread email the poller cannot process:
- Same identity fields as `EmailMessage` (no body/pdfs — not downloaded)
- `reason` — human-readable explanation (e.g. `"no attachments"`, `"no PDF attachments (found: image.png (image/png))"`)

Implementations:

| Class | Use case |
|-------|----------|
| `EmlFileSource` | CLI / testing — wraps a local `.eml` file |
| `GraphMailSource` | Production — polls M365 shared mailbox via Graph API |

### Graph API Query

```
GET /users/{mailbox}/messages
    ?$filter=isRead eq false
    &$expand=attachments
    &$select=id,internetMessageId,subject,from,receivedDateTime,body,hasAttachments
    &$top=10
```

All unread messages are fetched (no server-side attachment filter) so the poller can log and record a reason for every email it skips. Graph still does the `isRead eq false` filter server-side — the poller never sees read messages or the full mailbox history. `$top=10` caps each request.

### Graph API Authentication

CatPro is a separate M365 tenant. Uses `msal.ConfidentialClientApplication` with **client credentials flow** (application permissions, no user interaction).

**Azure AD prerequisites** (manual setup in CatPro tenant):
1. Register application → tenant ID + client ID
2. Add API permissions: `Mail.Read`, `Mail.ReadWrite`, `Mail.Send` (Application type)
3. Grant admin consent (via `az rest` app role assignments)
4. Create client secret → store in `.env`
5. (Recommended) Application access policy to restrict to shared mailbox only

### Non-Claim Email Handling

This mailbox is **shared between the poller and humans**. Customers send claim PDFs but also follow-up questions and status inquiries. The poller must leave all non-claim emails completely untouched.

| Email type | Poller action |
|---|---|
| Has PDF attachments | Process → mark read → move to "Processed" folder |
| No attachments | Record as `skipped` in DB (first time only), leave untouched in inbox |
| Has attachments, no PDFs | Record as `skipped` in DB (first time only), leave untouched in inbox |
| Has PDFs, processing fails | Leave unread in inbox for manual review; record as `error` in DB |

Skip dedup: on every poll cycle, `poll_once()` checks `_is_duplicate(internet_message_id)` before logging or recording a skipped email. Each unique non-claim email is logged **exactly once** across the poller's lifetime (including restarts). Subsequent cycles are completely silent for already-seen emails.

### Post-Processing (Claim Emails)

- **Success**: email marked read and moved to **"Processed"** folder (auto-created by Graph API)
- **Failure**: email left unread in inbox for manual review; error recorded in DB

### Error Handling

- **Session expiry**: re-authenticates to FileTrac with one retry
- **Graph API token refresh**: automatic on 401
- **TOTP safety**: single FileTrac session reused across all messages in a poll cycle
- **mark_read failure**: logged as warning, does not affect claim success status

## Phase 3: FastAPI + React Dashboard (Implemented)

The poller runs as a managed subprocess under a FastAPI backend, with a React/Vite dashboard for monitoring and control.

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│  FastAPI (uvicorn, port 8175)                           │
│                                                         │
│  routes.py ──── REST API /api/v1/*                      │
│  poller_manager.py ── subprocess lifecycle              │
│       │                                                 │
│       │  spawns                                         │
│       ▼                                                 │
│  scripts/poll.py → app.services.poller.Poller           │
│       │  while True: poll_once() → _sleep()             │
│       │  reads poll_interval_seconds from DB each sec   │
│       ▼                                                 │
│  app.services.email_source.GraphMailSource              │
│       │  fetch_unread() → (messages, skipped)           │
│       ▼                                                 │
│  app.services.pdf_extractor + filetrac_submit           │
│       │  extract → auth → submit                        │
│       ▼                                                 │
│  SQLite (data/claims.db) — WAL mode                     │
│       processed_emails + claim_data + app_config        │
└─────────────────────────────────────────────────────────┘
         ▲
         │  /api/v1/*  (Caddy → localhost:8175)
         ▼
┌─────────────────────────────────────────────────────────┐
│  React/Vite dashboard (port 5175)                       │
│  catpro.loc → Caddy → backend + frontend                │
│                                                         │
│  Dashboard — claims overview + trends                   │
│  Claims    — table with search/filter/detail            │
│  Admin: Settings / Polling / Testing                    │
└─────────────────────────────────────────────────────────┘
```

### Poller Subprocess Design (`backend/app/poller_manager.py`)

The FastAPI process manages the poller as a child subprocess:

- `start()` — kills any orphaned `scripts.poll` processes via `pgrep` (not just the PID file), then spawns `python3.13 -m scripts.poll` from `backend/` directory with a new session (`start_new_session=True`)
- `stop()` — `SIGTERM` with 10s timeout, then `SIGKILL`
- Logs to `logs/poller.log` (rotating, 10 MB × 5 backups)
- PID tracked in `logs/poller.pid` (gitignored)
- `_proc` is module-level — survives request/response cycles but resets on uvicorn restart (stale process cleanup handles orphans)

The `pgrep`-based orphan kill is critical: if uvicorn is hard-killed (`kill <pid>`), the poller subprocess survives as an orphan with PPID=1. On next `start()`, `pgrep scripts.poll` finds and terminates all such orphans before spawning a fresh one.

### SQLite Schema

Managed by Alembic migrations (`backend/alembic/versions/`). Three tables:

```sql
-- Singleton runtime configuration (id always = 1)
CREATE TABLE app_config (
    id                    INTEGER PRIMARY KEY DEFAULT 1,
    dry_run               BOOLEAN NOT NULL DEFAULT 0,
    test_mode             BOOLEAN NOT NULL DEFAULT 0,
    test_adjuster_id      TEXT DEFAULT '342436',
    test_branch_id        TEXT DEFAULT '2529',
    poller_enabled        BOOLEAN NOT NULL DEFAULT 1,
    poll_interval_seconds INTEGER NOT NULL DEFAULT 60,  -- live config, read by poller each cycle
    poller_status         TEXT,    -- 'idle' | 'running' | 'error' | 'disabled'
    last_heartbeat        TEXT,    -- ISO 8601, updated every cycle
    last_run_at           TEXT,    -- ISO 8601, updated after each poll_once()
    last_error            TEXT,    -- last exception message, null on success
    updated_at            TEXT     -- ISO 8601, set on every PUT /config
);

-- One row per email the poller has seen
CREATE TABLE processed_emails (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id          TEXT NOT NULL,      -- Graph API message ID
    internet_message_id TEXT NOT NULL UNIQUE, -- RFC 2822 Message-ID (dedup key)
    subject             TEXT,
    sender              TEXT,
    received_at         TEXT,
    processed_at        TEXT NOT NULL,
    claim_id            TEXT,               -- "claimID=NNNNNNN" | "DRY_RUN" | null
    status              TEXT NOT NULL,      -- pending | success | error | skipped
    error_message       TEXT,               -- exception or skip reason
    dry_run             BOOLEAN DEFAULT 0
);

-- One row per successfully extracted claim (joined to processed_emails)
CREATE TABLE claim_data (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id                INTEGER NOT NULL REFERENCES processed_emails(id),
    -- Extracted fields (30 total: insured, loss, client, agent, policy)
    insured_first_name TEXT, insured_last_name TEXT, ...
    -- Resolved FileTrac IDs
    filetrac_company_id TEXT, filetrac_contact_id TEXT, filetrac_branch_id TEXT,
    filetrac_adjuster_id TEXT, filetrac_manager_id TEXT, filetrac_csrf_token TEXT,
    -- Full submission payload as JSON (~80 form fields)
    submission_payload  TEXT,
    created_at          TEXT NOT NULL
);
```

### Poll Interval — Live Configuration

`poll_interval_seconds` is stored in `app_config` (default 60). The poller's sleep loop re-reads it from the DB **every second**:

```python
elapsed = 0
while self._running:
    interval = self._get_poll_interval()  # DB read each second
    if elapsed >= interval:
        break
    time.sleep(1)
    elapsed += 1
```

Changing the interval via `PUT /api/v1/config` takes effect within 1 second — no restart needed.

### REST API

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/config` | Singleton `AppConfig` |
| PUT | `/api/v1/config` | Partial update (`dry_run`, `test_mode`, `poll_interval_seconds`, `poller_enabled`, etc.) |
| GET | `/api/v1/poller/status` | `{running: bool, pid: int\|null}` |
| POST | `/api/v1/poller/start` | Spawn poller subprocess |
| POST | `/api/v1/poller/stop` | Terminate poller |
| GET | `/api/v1/poller/logs` | Last N lines from `logs/poller.log` |
| DELETE | `/api/v1/poller/logs` | Truncate log file |
| POST | `/api/v1/poller/send-test-email` | Send mock Acuity email to test mailbox |
| GET | `/api/v1/claims` | Paginated claims with search, filter, inline stats |
| GET | `/api/v1/claims/{id}` | Full claim detail (CSRF token + SSN fields redacted) |
| GET | `/api/v1/claims/trends` | Daily volume for chart (last 30 days, zero-filled) |
| GET | `/api/v1/health` | Heartbeat recency + recent error rate |

### DRY_RUN and TEST_MODE

Both stored in `app_config`, togglable via UI without restart:

| | `DRY_RUN=false` | `DRY_RUN=true` |
|---|---|---|
| `TEST_MODE=false` | Production: real IDs, real claim created in FileTrac | Preview: real IDs resolved, no POST |
| `TEST_MODE=true` | Test claim: Bob TEST adjuster + TEST branch, claim created | Dev: test IDs, no POST |

### Local Dev Routing

Caddy reverse proxy at `/opt/homebrew/etc/Caddyfile`:

```
http://catpro.loc {
    reverse_proxy /api/* localhost:8175   # FastAPI
    reverse_proxy localhost:5175          # Vite dev server
}
```

Reload: `caddy reload --config /opt/homebrew/etc/Caddyfile`

### Entry Points

```bash
# Backend (from backend/)
python3.13 -m uvicorn app.main:app --port 8175 --host 127.0.0.1

# Frontend (from frontend/)
npm run dev

# Poller (spawned by poller_manager, but also runnable directly from backend/)
python3.13 -m scripts.poll

# CLI — single EML file (still works, from repo root)
python3.13 -m catpro.process_claim email.eml

# Send test email (from backend/)
python3.13 -m scripts.test_email --ref 0001 --adjuster "Doug"
```

## Security

- All credentials in `.env` (gitignored): `FILETRAC_EMAIL`, `FILETRAC_PASSWORD`, `FILETRAC_TOTP_SECRET`, `AZURE_*`
- No credentials in logs, stdout, or committed files
- `adjusters.json` contains no credentials — safe to commit
- Azure AD app should be scoped to shared mailbox only via application access policy

## File Structure

```
catpro/                         — Legacy standalone CLI package (Phase 1)
  __init__.py
  process_claim.py              — Core pipeline: parse, extract, auth, submit
  email_source.py               — EmailSource Protocol + EmlFileSource (CLI only)
  db.py                         — Raw SQLite helpers (CLI only)
  config.py                     — Pydantic settings from .env (CLI only)
  test_email.py                 — Send test emails via Graph API (CLI)
  adjusters.json                — Adjuster name → FileTrac ID mapping

backend/                        — FastAPI application (Phase 3)
  app/
    main.py                     — FastAPI app, CORS middleware, router mount
    routes.py                   — All REST endpoints (/api/v1/*)
    models.py                   — SQLAlchemy ORM: AppConfig, ProcessedEmail, ClaimData
    schemas.py                  — Pydantic request/response schemas
    database.py                 — SQLite engine, WAL mode, SessionLocal, get_db
    config.py                   — Pydantic Settings from .env (backend-specific)
    poller_manager.py           — Poller subprocess lifecycle (start/stop/logs/pid)
    services/
      poller.py                 — THE canonical polling loop (entry: scripts.poll)
      email_source.py           — EmailSource Protocol + EmlFileSource + GraphMailSource
      eml_parser.py             — MIME parse: extract body + PDF attachments
      pdf_extractor.py          — Acuity PDF parsing via pdfplumber
      filetrac_auth.py          — Cognito SRP + TOTP + evolveLogin SSO
      filetrac_submit.py        — Dynamic ID resolution + POST claimSave.asp
      test_email.py             — Send test emails via Graph API (backend)
  alembic/
    versions/                   — Schema migrations (one file per change)
  scripts/
    poll.py                     — Entry point: python -m scripts.poll

frontend/                       — React/Vite/TailwindCSS dashboard (Phase 3)
  src/
    pages/
      Dashboard.tsx             — Claims overview + trend chart
      Claims.tsx                — Paginated table with search/filter
      admin/
        Settings.tsx            — Dry run toggle
        Polling.tsx             — Poller control, interval config, status, logs
        Testing.tsx             — Send test emails
    components/
      admin/shared.tsx          — Toggle, SettingRow, InfoRow, PollerStatusBadge
      claims/                   — ClaimsTable, ClaimModal
      ui.tsx                    — SectionHeading, shared primitives
    hooks/
      useAppConfig.ts           — useAppConfig(), useUpdateAppConfig()
      usePoller.ts              — usePollerStatus/Start/Stop/Logs/ClearLogs/SendTestEmail
    schemas/claim.ts            — Zod schemas + inferred TypeScript types
    lib/api.ts                  — Axios instance pointed at /api/v1

data/                           — Runtime data (gitignored except .gitkeep)
  claims.db                     — SQLite database (created at runtime)
  templates/
    sample_acuity_claim.eml     — Mock Acuity claim with fake data (for testing)

logs/                           — Runtime logs (gitignored)
  poller.log                    — Rotating poller log (10 MB × 5 backups)
  poller.pid                    — Subprocess PID (gitignored)

.env                            — All credentials (gitignored)
docs/
  product-requirements.md       — Business context and requirements
  architecture.md               — This document
```
