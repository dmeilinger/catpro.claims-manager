---
title: FileTrac Claim Automation — EML File Reader
type: feat
status: active
date: 2026-03-30
origin: docs/brainstorms/2026-03-30-filetrac-claim-automation-brainstorm.md
---

# FileTrac Claim Automation — EML File Reader

## Overview

A Python script (`process_claim.py`) that accepts an `.eml` file path, extracts all claim data from the email body and PDF attachments using the Claude API, and automatically creates the claim in FileTrac via HTTP POST — no browser, no manual data entry.

First target: `Fw_ TG4832.eml` (Acuity Insurance, claim TG4832, insured Ellebracht/Hirchak).

(see brainstorm: docs/brainstorms/2026-03-30-filetrac-claim-automation-brainstorm.md)

## Proposed Solution

Three composable modules in a single script:

1. **`parse_eml(path)`** — MIME parse the `.eml`, extract email body text + classify PDF attachments by filename
2. **`extract_claim_fields(email_body, pdfs)`** — Send all PDFs + body to Claude API, return structured `ClaimData` Pydantic model
3. **`submit_claim(claim_data)`** — Authenticate to FileTrac (login → TOTP → session), fetch CSRF token, POST claim form

## Implementation Phases

### Phase 1: EML Parsing & PDF Extraction

**File:** `process_claim.py`

Use Python's stdlib `email` module to walk MIME parts. Classify PDFs by filename substring:
- `"Claim Summary"` → claim summary
- `"Loss Notice"` → loss notice
- `"Policy Summary"` → policy summary
- Unrecognized → included unlabeled (Claude identifies them)

```python
import email
from pathlib import Path

def parse_eml(eml_path: str) -> tuple[str, dict[str, bytes]]:
    """Returns (email_body_text, {doc_type: pdf_bytes})"""
    with open(eml_path, 'rb') as f:
        msg = email.message_from_bytes(f.read())

    body = ""
    pdfs = {}

    for part in msg.walk():
        ct = part.get_content_type()
        fname = part.get_filename() or ""

        if ct == 'text/plain' and not fname:
            body += part.get_payload(decode=True).decode('utf-8', errors='replace')

        elif ct == 'application/pdf':
            data = part.get_payload(decode=True)
            if 'Claim Summary' in fname:
                pdfs['claim_summary'] = data
            elif 'Loss Notice' in fname:
                pdfs['loss_notice'] = data
            elif 'Policy Summary' in fname:
                pdfs['policy_summary'] = data
            else:
                pdfs[fname] = data  # unknown, pass to Claude labeled by filename

    return body, pdfs
```

### Phase 2: Claude API Extraction

**Model:** `claude-sonnet-4-6` (sufficient for structured extraction, faster/cheaper than opus)

**Method:** Pydantic model + `client.messages.parse()` with structured output

**Key design decisions (see brainstorm):**
- Send all PDFs + email body in a single API call
- Use Pydantic model for type-safe structured output
- `None` for fields not found in any source document
- Document blocks go before the text prompt

```python
import base64
import anthropic
import pydantic

class ClaimData(pydantic.BaseModel):
    # From Claim Summary PDF
    client_claim_number: str | None = None        # → companyFileID
    insured_first_name: str | None = None         # → insuredFName
    insured_last_name: str | None = None          # → insuredLName
    insured_email: str | None = None              # → insuredEMail
    insured_phone: str | None = None              # → insuredPhone
    insured_cell: str | None = None               # → insuredPhone3
    insured_address1: str | None = None           # → insuredAddr1
    insured_city: str | None = None               # → insuredCity
    insured_state: str | None = None              # → insuredState (2-letter)
    insured_zip: str | None = None                # → insuredZIP
    policy_number: str | None = None              # → insuredPolicyNum
    secondary_insured_first: str | None = None    # → secondaryInsuredFName
    secondary_insured_last: str | None = None     # → secondaryInsuredLName
    # From Loss Notice PDF
    loss_date: str | None = None                  # → lossDate (MM/DD/YYYY)
    loss_type: str | None = None                  # → lossType (Hail/Wind/Fire/etc.)
    loss_description: str | None = None           # → loss description textarea
    loss_address1: str | None = None              # → lossAddr1
    loss_city: str | None = None                  # → lossCity
    loss_state: str | None = None                 # → lossState
    loss_zip: str | None = None                   # → lossZIP
    # From email body
    assigned_adjuster_name: str | None = None     # → ACuserID (needs ID lookup)
    # Agent info
    agent_company: str | None = None              # → agentCompany
    agent_phone: str | None = None                # → agentPhone1
    agent_email: str | None = None                # → agentEMail
    agent_address1: str | None = None             # → agentAddr1
    agent_city: str | None = None                 # → agentCity
    agent_state: str | None = None                # → agentState
    agent_zip: str | None = None                  # → agentZIP
    # Client company (insurer)
    client_company_name: str | None = None        # → companyIDTxt (e.g. "Acuity Insurance")


def extract_claim_fields(email_body: str, pdfs: dict[str, bytes]) -> ClaimData:
    client = anthropic.Anthropic()

    content = []

    # Add each PDF as a document block (before the text prompt)
    for doc_type, pdf_bytes in pdfs.items():
        pdf_b64 = base64.standard_b64encode(pdf_bytes).decode('utf-8')
        label = doc_type.replace('_', ' ').title()
        content.append({
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": pdf_b64,
            },
            "title": label,
            "cache_control": {"type": "ephemeral"},
        })

    content.append({
        "type": "text",
        "text": f"""Extract all claim fields from the attached documents and email body.

EMAIL BODY:
{email_body}

Instructions:
- Extract fields precisely as they appear
- Dates should be in MM/DD/YYYY format
- State codes should be 2-letter abbreviations
- Phone numbers as digits only (no formatting)
- For assigned_adjuster_name: extract the first name mentioned in the email body as the adjuster
- For loss_type: use one of: Hail, Wind, Fire, Flood, Water, Theft, Vandalism, Other
- Use null for any field not found in any document
""",
    })

    parsed = client.messages.parse(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        output_format=ClaimData,
        messages=[{"role": "user", "content": content}],
    )
    return parsed.parsed_output
```

### Phase 3: FileTrac Authentication

**⚠️ MFA endpoint URL is unknown** — must be intercepted via browser network inspection before this phase can be completed. Use the chrome-devtools MCP to record the login network requests.

Expected flow based on exploration (see brainstorm):

```python
import pyotp
import requests
import os
import time
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

TIMEOUT = (10, 30)
LOGIN_URL = "https://ftevolve.com/auth/login"
MFA_URL = "https://ftevolve.com/auth/mfa"        # ⚠️ NEEDS VERIFICATION
CLAIM_FORM_URL = "https://cms14.filetrac.net/system/claimAdd.asp"

def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; CatPro-Automation/1.0)",
        "Accept": "text/html,application/xhtml+xml,*/*",
        "Accept-Language": "en-US,en;q=0.5",
    })
    return session

def get_totp_code() -> str:
    """Generate TOTP, waiting if too close to window boundary."""
    secret = os.environ["FILETRAC_TOTP_SECRET"]
    totp = pyotp.TOTP(secret)
    # Wait if < 5 seconds left in current window (avoids stale code on transit)
    time_remaining = 30 - (int(time.time()) % 30)
    if time_remaining < 5:
        time.sleep(time_remaining + 1)
    return totp.now()

def login(session: requests.Session) -> None:
    """Authenticate to FileTrac — login + TOTP MFA."""
    # Step 1: GET login page (sets pre-auth cookies)
    resp = session.get(LOGIN_URL, timeout=TIMEOUT)
    resp.raise_for_status()

    # Step 2: POST credentials
    resp = session.post(LOGIN_URL, data={
        "email": os.environ["FILETRAC_EMAIL"],
        "password": os.environ["FILETRAC_PASSWORD"],
    }, timeout=TIMEOUT, allow_redirects=True)
    resp.raise_for_status()

    # Step 3: POST TOTP  ⚠️ endpoint + field names need verification
    resp = session.post(MFA_URL, data={
        "mfa_code": get_totp_code(),
        "remember_device": "1",
    }, timeout=TIMEOUT, allow_redirects=True)
    resp.raise_for_status()

    # Verify we landed on FileTrac (not back on login)
    if "filetrac" not in resp.url.lower() and "login" in resp.url.lower():
        raise RuntimeError(f"Login failed — still on login page: {resp.url}")
```

### Phase 4: CSRF Token + Claim Submission

```python
def extract_csrf_token(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("input", attrs={"type": "hidden", "name": "pageLayout_CSRtoken"})
    if not tag or not tag.get("value"):
        raise RuntimeError("CSRF token not found in claimAdd.asp — session may be expired")
    return tag["value"]

def resolve_adjuster_id(session: requests.Session, adjuster_name: str) -> str:
    """
    Map adjuster name to FileTrac user ID.
    Phase 1: use local mapping file (adjusters.json).
    Phase 2: query FileTrac user search endpoint if discovered.
    """
    import json
    mapping_path = Path(__file__).parent / "adjusters.json"
    if mapping_path.exists():
        mapping = json.loads(mapping_path.read_text())
        # Case-insensitive partial match
        for name, uid in mapping.items():
            if adjuster_name.lower() in name.lower():
                return uid
    # Default: UNASSIGNED
    return "0"

def submit_claim(session: requests.Session, claim: ClaimData) -> str:
    """Submit claim to FileTrac. Returns new claim file number."""
    from datetime import date

    # GET claim form to extract CSRF token
    resp = session.get(CLAIM_FORM_URL, timeout=TIMEOUT)
    resp.raise_for_status()
    csrf_token = extract_csrf_token(resp.text)

    adjuster_id = resolve_adjuster_id(session, claim.assigned_adjuster_name or "")

    payload = {
        # Required hidden fields (see brainstorm)
        "pageLayout_CSRtoken": csrf_token,
        "ashish": "1",
        "ACuserID_inputType": "SELECT",
        "prefixID": "##AUTO",
        "tennessee": "0",
        "ackALERT": "0",
        "workQID": "0",
        # Date received = today
        "claimDateReceived": date.today().strftime("%m/%d/%Y"),
        # Claim fields from extraction
        "companyFileID": claim.client_claim_number or "",
        "companyIDTxt": claim.client_company_name or "",
        "insuredFName": claim.insured_first_name or "",
        "insuredLName": claim.insured_last_name or "",
        "insuredEMail": claim.insured_email or "",
        "insuredPhone": claim.insured_phone or "",
        "insuredPhone3": claim.insured_cell or "",
        "insuredAddr1": claim.insured_address1 or "",
        "insuredCity": claim.insured_city or "",
        "insuredState": claim.insured_state or "",
        "insuredZIP": claim.insured_zip or "",
        "insuredPolicyNum": claim.policy_number or "",
        "secondaryInsuredFName": claim.secondary_insured_first or "",
        "secondaryInsuredLName": claim.secondary_insured_last or "",
        "lossDate": claim.loss_date or "",
        "lossType": claim.loss_type or "",
        "lossAddr1": claim.loss_address1 or "",
        "lossCity": claim.loss_city or "",
        "lossState": claim.loss_state or "",
        "lossZIP": claim.loss_zip or "",
        "agentCompany": claim.agent_company or "",
        "agentPhone1": claim.agent_phone or "",
        "agentEMail": claim.agent_email or "",
        "agentAddr1": claim.agent_address1 or "",
        "agentCity": claim.agent_city or "",
        "agentState": claim.agent_state or "",
        "agentZIP": claim.agent_zip or "",
        "ACuserID": adjuster_id,
    }

    resp = session.post(CLAIM_FORM_URL, data=payload, timeout=TIMEOUT, allow_redirects=True)
    resp.raise_for_status()

    # Verify success — look for claim file number in response
    soup = BeautifulSoup(resp.text, "html.parser")
    # ⚠️ Success response parsing needs verification against actual FileTrac response
    # Look for a file number pattern like "26-XXXXX"
    import re
    match = re.search(r'\b(2[0-9]-\d{5})\b', resp.text)
    if match:
        return match.group(1)

    # Check we didn't get redirected back to claim form (sign of failure)
    if "claimAdd.asp" in resp.url:
        raise RuntimeError("Claim submission failed — returned to claim form")

    return "submitted (file number not parsed)"
```

### Phase 5: Main Entry Point

```python
def main():
    import sys

    if len(sys.argv) != 2:
        print("Usage: python process_claim.py <path/to/email.eml>")
        sys.exit(1)

    eml_path = sys.argv[1]

    print(f"[1/4] Parsing {eml_path}...")
    email_body, pdfs = parse_eml(eml_path)
    print(f"      Found {len(pdfs)} PDF(s): {list(pdfs.keys())}")

    print("[2/4] Extracting claim fields via Claude API...")
    claim = extract_claim_fields(email_body, pdfs)
    print(f"      Insured: {claim.insured_first_name} {claim.insured_last_name}")
    print(f"      Policy:  {claim.policy_number}")
    print(f"      Loss:    {claim.loss_date} — {claim.loss_type}")

    print("[3/4] Authenticating to FileTrac...")
    session = build_session()
    login(session)
    print("      Authenticated.")

    print("[4/4] Submitting claim...")
    file_number = submit_claim(session, claim)
    print(f"      ✓ Claim created: {file_number}")

if __name__ == "__main__":
    main()
```

## Files to Create

| File | Purpose |
|------|---------|
| `process_claim.py` | Main script (all phases above) |
| `requirements.txt` | Python dependencies |
| `adjusters.json` | Name → FileTrac user ID mapping (operator maintained) |

## requirements.txt

```
anthropic>=0.40.0
requests>=2.31.0
pyotp>=2.9.0
python-dotenv>=1.0.0
beautifulsoup4>=4.12.0
pydantic>=2.0.0
```

## Acceptance Criteria

- [ ] `python process_claim.py "Fw_ TG4832.eml"` runs end to end without error
- [ ] Claim appears in FileTrac with correct insured name, policy number, loss date, and loss location
- [ ] Script exits non-zero on any error (auth failure, extraction failure, submission failure)
- [ ] No credentials appear in logs or stdout
- [ ] TOTP auth works without manual intervention

## Open Questions (must resolve before Phase 3)

| Question | How to Resolve |
|----------|---------------|
| Exact MFA POST endpoint URL and field names | Inspect network requests during manual login via chrome-devtools MCP |
| `companyIDTxt` autocomplete — does raw POST work or need XHR? | Inspect network during company field interaction in browser |
| FileTrac success response format (what does it look like after claim created?) | Submit a test claim manually and inspect the response page |
| `stormID` — required for storm claims? | Check if field has a default; inspect form behavior |
| Adjuster ID lookup — is there a search endpoint? | Inspect network during adjuster dropdown interaction |

## Security Notes

- All credentials via `.env` — never hardcoded or logged
- `.env` already in project root with correct keys
- `adjusters.json` contains no credentials — safe to commit
- TOTP secret is treated as a credential — same `.env` handling

## Dependencies & Risks

| Risk | Mitigation |
|------|-----------|
| MFA endpoint unknown | Resolve via browser network inspection before writing auth code |
| companyIDTxt may require JS autocomplete | If POST with name fails, intercept the autocomplete XHR and replicate it |
| Auto-save on claimAdd.asp | Never interact with the form in browser while building — pure HTTP only |
| TOTP window expiry | `get_totp_code_safe()` waits if < 5s remaining in window |
| FileTrac session expiry mid-run | Re-authenticate and retry once on 401/redirect-to-login |

## Sources & References

- **Origin brainstorm:** [docs/brainstorms/2026-03-30-filetrac-claim-automation-brainstorm.md](../brainstorms/2026-03-30-filetrac-claim-automation-brainstorm.md)
  Key decisions carried forward: HTTP-only (no browser), fully automatic (no approval step), file-based input (webhooks deferred), claude-sonnet-4-6 for extraction
- Anthropic Python SDK — PDF document blocks: `anthropic.types.Base64PDFSource`
- Anthropic Python SDK — Structured output: `client.messages.parse()` with Pydantic
- `pyotp` TOTP generation: RFC 6238 compliant, 30-second window
- FileTrac claim form: `https://cms14.filetrac.net/system/claimAdd.asp`
- Test email: `Fw_ TG4832.eml` (Acuity Insurance, Ellebracht/Hirchak, hail/storm roof damage)
