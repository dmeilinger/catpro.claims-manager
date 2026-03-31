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

## Authentication

Fully implemented in `process_claim.py`. Three-step flow:

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

## Entry Point

```bash
python3.13 process_claim.py Fw_TG4832.eml
```

Or programmatically:
```python
from process_claim import parse_eml, extract_claim_fields, build_session, login, submit_claim
body, pdfs = parse_eml('email.eml')
claim = extract_claim_fields(body, pdfs)
session = build_session()
login(session)
result = submit_claim(session, claim)  # returns "claimID=NNNNNNN"
```

## Next Phase: MS O365 Integration

Replace file-based EML input with Microsoft 365 email trigger:
- Watch a shared mailbox (e.g. claims@catpro.us.com) via MS Graph API / webhooks
- On new email with PDF attachments → pipe through `process_claim.py` pipeline
- Relevant M365 MCP tools available: `mcp__claude_ai_Microsoft_365__*`

## Browser Automation (exploration only)

- MCP server: `mcp__chrome-devtools__*` (configured globally in `~/.claude/settings.json`)
- Launches headless Chromium — no extension needed
- If stale process: `pkill -f "chrome-devtools-mcp"; pkill -f "chrome-profile"`
