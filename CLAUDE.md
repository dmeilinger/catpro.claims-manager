# FileTrac Claim Automation

## Reference Documents

- [Product Requirements](docs/product-requirements.md) — business context, goals, scope, and success criteria
- [Architecture](docs/architecture.md) — technical design, data flow, key constants, and implementation notes

## Project Goal
Build an agent that reads incoming claim emails and automatically creates claims in FileTrac (cms14.filetrac.net) — no manual data entry.

## System Overview

- **FileTrac CMS**: https://cms14.filetrac.net (legacy ASP system, hosted by Evolution Global)
- **Auth portal**: https://ftevolve.com (AWS Cognito + SSO bridge)
- **Company**: CatPro Insurance Services, LLC

## Python

Always use **`python3.13`** — system `python3` is 3.9, `pip3` targets 3.13.

## Project Structure

```
backend/                    — FastAPI application
  app/
    main.py                 — FastAPI app, CORS, router mount
    routes.py               — API endpoints
    schemas.py              — Pydantic request/response schemas
    models.py               — SQLAlchemy ORM models
    config.py               — Pydantic settings from .env
    database.py             — SQLAlchemy engine + SessionLocal
    poller_manager.py       — Background poller thread management
    services/
      email_source.py       — EmailSource Protocol + EmlFileSource + GraphMailSource
      poller.py             — M365 polling loop
      claim_processor.py    — Core pipeline: parse, extract, auth, submit
      eml_parser.py         — EML file parsing
      pdf_extractor.py      — PDF text extraction + field parsing
      filetrac_auth.py      — Cognito SRP + TOTP + evolveLogin SSO
      filetrac_submit.py    — FileTrac claim submission
      test_email.py         — Inject test emails into M365 mailbox
  alembic/                  — Database migrations
  scripts/
    poll.py                 — Poller entry point
    process_claim.py        — CLI: process a single EML file
    send_test_email.py      — CLI: inject test emails
  tests/                    — pytest test suite
frontend/                   — React + Vite dashboard
adjusters.json              — Adjuster name → FileTrac ID mapping
data/                       — Runtime data (gitignored except .gitkeep)
  claims.db                 — SQLite database (created at runtime)
  templates/
    sample_acuity_claim.eml — Mock Acuity claim with fake data (for testing)
.env                        — Credentials (gitignored)
docs/                       — Architecture and requirements
```

## Authentication

Fully implemented in `backend/app/services/filetrac_auth.py`. Three-step flow:

1. **AWS Cognito SRP** — `pycognito` handles SRP handshake + SOFTWARE_TOKEN_MFA challenge
2. **TOTP** — generated via `pyotp` from `FILETRAC_TOTP_SECRET`; window-boundary guard (waits if <5s remaining)
3. **evolveLogin SSO** — `POST https://cms14.filetrac.net/system/evolveLogin.asp` with `userId`, `evolveUserId` (Cognito sub), `access_token` → sets `ASPSESSIONID*` cookie

Cognito pool: `us-east-1_BOlb3igmv`, client ID: `1frtspmi2af7o8hqtfsfebrc6`
FileTrac legacy user ID (CatPro): `305873`

Credentials in `.env`:
```
FILETRAC_EMAIL=...
FILETRAC_PASSWORD=...
FILETRAC_TOTP_SECRET=...
```

**TOTP reuse**: running two logins within the same 30s window causes `ExpiredCodeException`. Don't run back-to-back logins manually.

## Claim Creation — WORKING

### Key URLs
- **Form page** (GET for CSRF token): `https://cms14.filetrac.net/system/claimAdd.asp`
- **Submit target**: `https://cms14.filetrac.net/system/claimSave.asp?newFlag=1&anotherFlag=0`
- **Autocomplete XHR**: `https://cms14.filetrac.net/system/claimEdit_clientList.asp`

### Flow
1. `login(session)` — Cognito + evolveLogin → ASPSESSIONID cookie
2. `GET claimAdd.asp` → extract `pageLayout_CSRtoken`
3. Resolve dynamic IDs via `claimEdit_clientList.asp`:
   - `?mode=customerCompanies&tgtCompany=<name>` → `companyID` (XML `<rs id='NNN'>`)
   - `?mode=customerReps&companyID=<id>` → `companyUserID` (first contact after header entry) + `companyEMail` (from header)
   - `?mode=customerBranches&companyID=<id>` → `ABID` (first `NNN##Branch Name`)
4. `POST claimSave.asp?newFlag=1&anotherFlag=0` with full ~80-field payload
5. Success: response body contains `<!-- claimID = [NNNNNNN] -->`

### ACmgrID
The `ACmgrID` select on `claimAdd.asp` has real manager options. `_parse_select_first_value()` skips placeholders (`-1`, `0`, `302465`, "Select", "UNASSIGNED", `---`). For CatPro, expected value is `319972` (Doug Hubby's manager ID).

### Adjuster lookup
`adjusters.json` maps `"Last, First"` → FileTrac user ID. Fallback: `302465` (UNASSIGNED).

## PDF Parsing (Acuity Insurance only)

`pdfplumber` extracts text; deterministic regex handles Acuity's two-column layout where right-column text gets injected into left-column lines. Handles:
- **Claim Summary**: insured name/address, policy #, loss date/location, agency block
- **Loss Notice**: loss description, loss address, date of loss
- **Policy Summary**: policy effective/expiration dates

LLM extraction not used — add later for other insurers.

## Entry Points

### API server
```bash
cd backend && python3.13 -m uvicorn app.main:app --port 8175 --host 127.0.0.1 --app-dir backend
```

### CLI (single file)
```bash
cd backend && python3.13 scripts/process_claim.py Fw_TG4832.eml
```

### Poller (M365 mailbox)
```bash
cd backend && python3.13 scripts/poll.py
```
Polls `M365_MAILBOX` for unread emails with PDF attachments, processes them through the claim pipeline, and tracks results in SQLite (`data/claims.db`).

### Test email generator
```bash
cd backend && python3.13 scripts/send_test_email.py                   # default mock, ref TG9999
cd backend && python3.13 scripts/send_test_email.py --ref 0001         # custom ref number
cd backend && python3.13 scripts/send_test_email.py --adjuster "Doug"  # custom adjuster name
```
Sends a real email (via Graph API `sendMail`) to the test mailbox with mock Acuity PDFs.

### Tests
```bash
cd backend && python3.13 -m pytest tests/ -v
```

## M365 Email Polling

- **`backend/app/services/email_source.py`**: `EmailSource` Protocol + `EmlFileSource` (CLI) + `GraphMailSource` (Graph API via `msal`)
- **`backend/app/models.py`**: SQLAlchemy ORM — `processed_emails`, `claim_data`, `email_actions` tables
- **`backend/app/config.py`**: Pydantic `Settings` loading all `.env` vars
- **`backend/app/services/poller.py`**: `while True` loop with SIGTERM handling for Docker

Processed emails are marked read and moved to a **"Processed"** folder in the mailbox (auto-created). Failed emails stay unread in inbox for manual review.

### Azure AD Setup

CatPro tenant app registration: `FileTrac Claim Poller` (app ID `7d22b1a4-b8de-4e14-a1af-bf9ffc235ea7`).
Permissions: `Mail.Read`, `Mail.ReadWrite`, `Mail.Send` (application). See `docs/architecture.md` for setup steps.

Azure CLI tenant isolation:
```bash
az-catpro <command>    # uses ~/.azure/catpro config dir
az-litera <command>    # uses ~/.azure/litera config dir
```

### Additional `.env` variables
```
AZURE_TENANT_ID=<catpro-tenant-guid>
AZURE_CLIENT_ID=<app-client-id>
AZURE_CLIENT_SECRET=<app-secret>
M365_MAILBOX=claims-test@catpro.us.com
POLL_INTERVAL_SECONDS=60
DB_PATH=data/claims.db
DRY_RUN=true
TEST_MODE=true
TEST_ADJUSTER_ID=342436
TEST_BRANCH_ID=2529
```

### DRY_RUN mode

`DRY_RUN=true` runs the full pipeline (poll, parse, extract, auth, CSRF, resolve IDs) but skips the final `POST claimSave.asp`. No billable claim created. All extracted data and the would-be payload are still saved to SQLite. Set `DRY_RUN=false` for production.

### TEST_MODE

`TEST_MODE=true` overrides resolved FileTrac IDs with test account values before payload construction. This is **separate from DRY_RUN** — they can be combined:

| | DRY_RUN=false | DRY_RUN=true |
|---|---|---|
| **TEST_MODE=false** | Production: real IDs, real claim | Preview: real IDs, no POST |
| **TEST_MODE=true** | Test claim: Bob TEST adjuster + TEST branch, claim created | Dev mode: test IDs, no POST |

Test account defaults (override in `.env`):
- `TEST_ADJUSTER_ID=342436` — Bob TEST (FileTrac Personnel Manager)
- `TEST_BRANCH_ID=2529` — TEST branch

For development, always use `DRY_RUN=true` + `TEST_MODE=true`.

## GitHub Remote

- **Origin**: `git@github-personal:dmeilinger/catpro.claims-manager.git`
- **SSH key**: `~/.ssh/id_dmeilinger_personal` (via `github-personal` host alias in `~/.ssh/config`)
- Always use SSH (not HTTPS) for GitHub operations — use `git@github-personal:dmeilinger/...` URLs, not `https://github.com/dmeilinger/...`

## Local Dev Routing (Caddy)

Caddy runs as a local reverse proxy for `*.loc` domains. Config: `/opt/homebrew/etc/Caddyfile`

```
http://catpro.loc {
    reverse_proxy /api/* localhost:8175   # FastAPI
    reverse_proxy localhost:5175          # Vite dev server
}
```

Reload after changes: `caddy reload --config /opt/homebrew/etc/Caddyfile`
DNS for `.loc` is handled by a local resolver (not `/etc/hosts`).
Vite must have `allowedHosts: ['catpro.loc']` in `vite.config.ts` or Caddy proxying will 403.

## FastAPI + Docker

The FastAPI app is running. The poller runs as a background thread managed by `backend/app/poller_manager.py`. See `docs/architecture.md` for full architecture.

## Browser Automation (exploration only)

- MCP server: `mcp__chrome-devtools__*` (configured globally in `~/.claude/settings.json`)
- Launches headless Chromium — no extension needed
- If stale process: `pkill -f "chrome-devtools-mcp"; pkill -f "chrome-profile"`
