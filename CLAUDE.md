# FileTrac Claim Automation

## Project Goal
Build an agent that reads incoming claim emails and automatically creates claims in FileTrac (cms14.filetrac.net) — no manual data entry.

## System Overview

- **FileTrac CMS**: https://cms14.filetrac.net (legacy ASP system, hosted by Evolution Global)
- **Auth portal**: https://ftevolve.com/auth/login (redirects to FTEvolve, then back to FileTrac)
- **Company**: CatPro Insurance Services, LLC

## Authentication

Three-step login flow — fully automatable via HTTP (no browser required at runtime):

1. **POST credentials** to ftevolve.com login endpoint → receive session cookie
2. **Generate TOTP** from secret (using `pyotp`) → POST to MFA endpoint
3. **Session cookie** is then valid for cms14.filetrac.net requests

Credentials and TOTP secret are stored in `.env`:
```
FILETRAC_EMAIL=...
FILETRAC_PASSWORD=...
FILETRAC_TOTP_SECRET=...
```

TOTP venv: `/tmp/totp-env` (has `pyotp` installed)

## Claim Creation

- **URL**: `https://cms14.filetrac.net/system/claimAdd.asp`
- **Method**: `POST application/x-www-form-urlencoded`
- **CSRF**: Each page load generates a fresh `pageLayout_CSRtoken` (GUID) that must be included in the POST
- **Auto-save**: The form auto-saves every minute and on field blur — be careful in browser exploration

### HTTP automation flow
1. Login → get session cookie
2. GET `claimAdd.asp` → extract `pageLayout_CSRtoken`
3. POST claim data + token + all required hidden fields

### Key form fields extracted from email

| Field | Form Name | Notes |
|-------|-----------|-------|
| Storm | `stormID` | dropdown |
| Client Company | `companyIDTxt` | autocomplete text |
| Client Contact | `companyUserID` | dropdown |
| Client Claim # | `companyFileID` | text |
| Date Received | `claimDateReceived` | date |
| Insured First Name | `insuredFName` | |
| Insured Last Name | `insuredLName` | |
| Insured Email | `insuredEMail` | |
| Insured Phone | `insuredPhone` | |
| Insured Address | `insuredAddr1`, `insuredAddr2`, `insuredCity`, `insuredState`, `insuredZIP` | |
| Policy # | `insuredPolicyNum` | |
| Policy Type | `PolicyType` | dropdown |
| Policy Effective Date | `insuredPolicyStart` | |
| Policy Expiration Date | `insuredPolicyEnd` | |
| Date of Loss | `lossDate` | |
| Type of Loss | `lossType` | Hail, Wind, Fire, Flood, etc. |
| Loss Location Address | `lossAddr1`, `lossAddr2`, `lossCity`, `lossState`, `lossZIP`, `lossCounty` | |
| Loss Description | textarea | |
| Type of Adjustment | `claimAdjType` | dropdown (e.g. Limited) |
| CAT Code | `claimCAT_select` | dropdown |
| Assign Adjuster | `ACuserID` | dropdown — large list |
| Assign Manager | `ACmgrID` | dropdown |
| Fee Schedule | `claimScheduleID` | dropdown |
| Special Instructions | textarea | |
| Deductible | `claimDeductable` | |
| Wind Deductible | `claimWindDeductable` | |
| Coverage A–D | `claimCoverageA`–`D` + type dropdowns | |

### Required hidden fields (must be included in POST)
- `pageLayout_CSRtoken` — fresh GUID from page load
- `ashish` = `1`
- `ACuserID_inputType` = `SELECT`
- `prefixID` = `##AUTO`
- `tennessee` = `0`
- `ackALERT` = `0`
- `workQID` = `0`
- Various `claimTime*` fields (default to current time)

## Browser Automation

Used for exploration only (not production automation):
- MCP server: `mcp__chrome-devtools__*` (configured globally in `~/.claude/settings.json`)
- Launches headless Chromium — no extension needed
- If stale process: `pkill -f "chrome-devtools-mcp"; pkill -f "chrome-profile"`

## Next Steps
1. Intercept actual login POST requests to map exact auth endpoints
2. Build Python HTTP client: login → get session → submit claim
3. Build email parser: extract claim fields from inbound email
4. Wire together as a Claude agent tool
