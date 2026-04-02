#!/usr/bin/env python3
"""
process_claim.py — FileTrac claim automation
Usage: python3 process_claim.py <path/to/email.eml>

Parses an EML file, extracts claim fields from Acuity Insurance PDFs
using deterministic text parsing, authenticates to FileTrac via AWS
Cognito + evolveLogin SSO, and submits the claim via HTTP POST.
"""

import base64
import email
import io
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

import pdfplumber
import pyotp
import pydantic
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from pycognito import Cognito

load_dotenv()

# ── Constants ──────────────────────────────────────────────────────────────────

COGNITO_USER_POOL_ID = "us-east-1_BOlb3igmv"
COGNITO_CLIENT_ID    = "1frtspmi2af7o8hqtfsfebrc6"
# FileTrac legacy IDs for CatPro (discovered via network interception)
FILETRAC_LEGACY_USER_ID   = "305873"
FILETRAC_LEGACY_SYSTEM_ID = "405"

EVOLVE_LOGIN_URL  = "https://cms14.filetrac.net/system/evolveLogin.asp"
CLAIM_FORM_URL    = "https://cms14.filetrac.net/system/claimAdd.asp"
CLAIM_SAVE_URL    = "https://cms14.filetrac.net/system/claimSave.asp?newFlag=1&anotherFlag=0"

TIMEOUT = (10, 30)


# ── Phase 1: EML Parsing ───────────────────────────────────────────────────────

def parse_eml(eml_path: str) -> tuple[str, dict[str, bytes]]:
    """Returns (email_body_text, {doc_type: pdf_bytes})"""
    with open(eml_path, "rb") as f:
        msg = email.message_from_bytes(f.read())

    body = ""
    pdfs = {}

    for part in msg.walk():
        ct    = part.get_content_type()
        fname = part.get_filename() or ""

        if ct == "text/plain" and not fname:
            body += part.get_payload(decode=True).decode("utf-8", errors="replace")

        elif ct == "application/pdf":
            data = part.get_payload(decode=True)
            # Normalize whitespace in filename (some clients wrap long names)
            fname_flat = " ".join(fname.split())
            if "Claim Summary" in fname_flat:
                pdfs["claim_summary"] = data
            elif "Loss Notice" in fname_flat:
                pdfs["loss_notice"] = data
            elif "Policy Summary" in fname_flat:
                pdfs["policy_summary"] = data
            else:
                pdfs[fname_flat or "attachment"] = data

    return body, pdfs


# ── Phase 2: Acuity PDF parsing ───────────────────────────────────────────────

class ClaimData(pydantic.BaseModel):
    # Insured
    insured_first_name:      str | None = None   # → insuredFName
    insured_last_name:       str | None = None   # → insuredLName
    insured_email:           str | None = None   # → insuredEMail
    insured_phone:           str | None = None   # → insuredPhone (digits only)
    insured_cell:            str | None = None   # → insuredPhone3
    insured_address1:        str | None = None   # → insuredAddr1
    insured_city:            str | None = None   # → insuredCity
    insured_state:           str | None = None   # → insuredState (2-letter)
    insured_zip:             str | None = None   # → insuredZIP
    policy_number:           str | None = None   # → insuredPolicyNum
    secondary_insured_first: str | None = None   # → secondaryInsuredFName
    secondary_insured_last:  str | None = None   # → secondaryInsuredLName
    # Loss
    loss_date:               str | None = None   # → lossDate (MM/DD/YYYY)
    loss_type:               str | None = None   # → lossType
    loss_description:        str | None = None   # → loss description textarea
    loss_address1:           str | None = None   # → lossAddr1
    loss_city:               str | None = None   # → lossCity
    loss_state:              str | None = None   # → lossState
    loss_zip:                str | None = None   # → lossZIP
    # Client (insurer company)
    client_company_name:     str | None = None   # → companyIDTxt
    client_claim_number:     str | None = None   # → companyFileID
    # Agent
    agent_company:           str | None = None   # → agentCompany
    agent_phone:             str | None = None   # → agentPhone1
    agent_email:             str | None = None   # → agentEMail
    agent_address1:          str | None = None   # → agentAddr1
    agent_city:              str | None = None   # → agentCity
    agent_state:             str | None = None   # → agentState
    agent_zip:               str | None = None   # → agentZIP
    # Assignment
    assigned_adjuster_name:  str | None = None   # → ACuserID (needs ID lookup)
    # Policy dates
    policy_effective:        str | None = None   # → insuredPolicyStart
    policy_expiration:       str | None = None   # → insuredPolicyEnd


def _pdf_text(pdf_bytes: bytes) -> str:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


def _digits(s: str) -> str:
    """Strip all non-digit characters from a phone number."""
    return re.sub(r"\D", "", s)


def _acuity_date(s: str) -> str:
    """Convert 08-01-2025 or 08/01/2025 to MM/DD/YYYY."""
    m = re.match(r"(\d{2})[-/](\d{2})[-/](\d{4})", s.strip())
    if m:
        return f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
    return s.strip()


def _parse_claim_summary(text: str, data: ClaimData) -> None:
    """
    Parse Acuity Claim Summary PDF text into data fields.
    Layout (from pdfplumber extraction):
      - Claim number in header: "Claim Number: TG4832"
      - Insured block: "LAST, FIRST\n& SECONDARY NAME\nADDR\nCITY STATE ZIP\nPHONE nnn.nnn.nnnn\n..."
      - Loss location: "Loss Location: ADDR CITY STATE\nZIP"
      - Loss date: "Loss Date: MM/DD/YYYY"
      - Policy: "Policy: XXXXXXX"
      - Agency block after "Agency:"
    """
    # Claim number
    m = re.search(r"Claim Number:\s*(\S+)", text)
    if m:
        data.client_claim_number = m.group(1)

    # Client company — always Acuity for this parser
    data.client_company_name = "Acuity Insurance"

    # Loss date
    m = re.search(r"Loss Date:\s*(\d{2}/\d{2}/\d{4})", text)
    if m:
        data.loss_date = m.group(1)

    # Loss location — "Loss Location: 2645 DERBY PL FLORISSANT MO\n63033"
    m = re.search(r"Loss Location:\s+(.+?)\s+([A-Z]{2})\s*\n(\d{5})", text, re.DOTALL)
    if m:
        addr_city = m.group(1).strip()
        data.loss_state = m.group(2)
        data.loss_zip   = m.group(3)
        # Split address from city — city is last word(s) before state; address is everything before
        # Format: "2645 DERBY PL FLORISSANT" — find last all-caps word as city
        parts = addr_city.rsplit(None, 1)
        if len(parts) == 2:
            data.loss_address1 = parts[0].title()
            data.loss_city     = parts[1].title()
        else:
            data.loss_address1 = addr_city.title()

    # Policy number
    m = re.search(r"\bPolicy:\s*(\S+)", text)
    if m:
        data.policy_number = m.group(1)

    # Insured block: lines immediately after "1 INSURED"
    # pdfplumber merges two-column layout, so right-column text may appear on same line.
    # Actual text:
    #   "ELLEBRACHT, KATHY\n"
    #   "& DEBORAH HIRCHAK General Policy/Loss Information\n"  ← right col appended
    #   "1277 S 3RD ST\n"
    #   "Loss Date: 08/01/2025\n"                              ← right col injected
    #   "TROY MO 63379\n"
    #   "PHONE 636.290.8124 Loss Location: ..."                ← right col appended
    m = re.search(
        r"1 INSURED\n"
        r"([A-Z][A-Z ,.']+)\n"                   # primary name  "ELLEBRACHT, KATHY"
        r"(& [A-Z][A-Z ]+[A-Z])(?:\s+\S.*?)?\n"   # secondary (ignore right-col suffix)
        r"(\d+[^\n]+)\n"                          # address       "1277 S 3RD ST"
        r"(?:[^\n]*\n)*?"                         # skip any injected right-col lines
        r"([A-Z][A-Z ]+?)\s+([A-Z]{2})\s+(\d{5})\n"  # "TROY MO 63379"
        r"PHONE ([\d.]+)",
        text
    )
    if not m:
        # Fallback: no secondary insured
        m = re.search(
            r"1 INSURED\n"
            r"([A-Z][A-Z ,.']+)\n"
            r"(\d+[^\n]+)\n"
            r"(?:[^\n]*\n)*?"
            r"([A-Z][A-Z ]+?)\s+([A-Z]{2})\s+(\d{5})\n"
            r"PHONE ([\d.]+)",
            text
        )
        if m:
            primary_name = m.group(1).strip()
            secondary    = None
            addr         = m.group(2).strip()
            city         = m.group(3).strip()
            state        = m.group(4)
            zip_code     = m.group(5)
            phone        = m.group(6)
        else:
            primary_name = secondary = addr = city = state = zip_code = phone = None
    else:
        primary_name = m.group(1).strip()
        secondary    = m.group(2)
        addr         = m.group(3).strip()
        city         = m.group(4).strip()
        state        = m.group(5)
        zip_code     = m.group(6)
        phone        = m.group(7)

    if primary_name:
        # Parse "LAST, FIRST" → first/last
        name_parts = primary_name.split(",", 1)
        if len(name_parts) == 2:
            data.insured_last_name  = name_parts[0].strip().title()
            data.insured_first_name = name_parts[1].strip().title()
        else:
            data.insured_last_name = primary_name.title()

        # Secondary insured: "& DEBORAH HIRCHAK" → first/last
        if secondary:
            sec = re.sub(r"^&\s*", "", secondary).strip()
            sec_parts = sec.split(None, 1)
            if len(sec_parts) == 2:
                data.secondary_insured_first = sec_parts[0].title()
                data.secondary_insured_last  = sec_parts[1].title()
            else:
                data.secondary_insured_last = sec.title()

        if addr:     data.insured_address1 = addr.title()
        if city:     data.insured_city     = city.title()
        if state:    data.insured_state    = state
        if zip_code: data.insured_zip      = zip_code
        if phone:    data.insured_phone    = _digits(phone)

    # Cell phone — from "INSURED CONTACT" block
    m = re.search(r"CELL ([\d.]+)", text)
    if m:
        data.insured_cell = _digits(m.group(1))

    # Email
    m = re.search(r"Email\s+(\S+@\S+)", text)
    if m:
        data.insured_email = m.group(1)

    # Agency block: "Agency: NAME\nADDR1\nADDR2\nCITY STATE ZIP\nPHONE ...\nFAX ...\nEmail ..."
    m = re.search(
        r"Agency:\s+\d+\s+(.+?)\n(.+?)\n(.+?)\n(\w[\w\s]+?)\s+([A-Z]{2})\s+(\d{5})\nPHONE ([\d.,\s]+)\n.*?Email\s+(\S+@\S+)",
        text, re.DOTALL
    )
    if m:
        data.agent_company  = m.group(1).strip().title()
        # addr lines — combine if both non-empty
        a1, a2 = m.group(2).strip(), m.group(3).strip()
        data.agent_address1 = f"{a1}, {a2}".title() if a2 else a1.title()
        data.agent_city     = m.group(4).strip().title()
        data.agent_state    = m.group(5)
        data.agent_zip      = m.group(6)
        data.agent_phone    = _digits(m.group(7).split(",")[0])
        data.agent_email    = m.group(8)

    # Loss type from description line
    desc_upper = text.upper()
    if "HAIL" in desc_upper:
        data.loss_type = "Hail"
    elif "WIND" in desc_upper or "STORM" in desc_upper:
        data.loss_type = "Wind"
    elif "FIRE" in desc_upper:
        data.loss_type = "Fire"
    elif "FLOOD" in desc_upper or "WATER" in desc_upper:
        data.loss_type = "Flood"


def _parse_loss_notice(text: str, data: ClaimData) -> None:
    """
    Parse Acuity Loss Notice (Claim Reporting Form) PDF.
    Fills in loss description, and verifies/supplements other fields.
    """
    # Description of Occurrence
    m = re.search(r"Description of Occurrence:\s*(.+?)\nAddress:", text, re.DOTALL)
    if m:
        data.loss_description = m.group(1).replace("\n", " ").strip()

    # Loss address — single-line "Address: 2645 Derby Place\nCity: Florissant State: MO Zip: 63033"
    m = re.search(r"^Address:\s*(.+)$\nCity:\s*(.+?)\s+State:\s*([A-Z]{2})\s+Zip:\s*(\d{5})", text, re.MULTILINE)
    if m:
        data.loss_address1 = m.group(1).strip().title()
        data.loss_city     = m.group(2).strip().title()
        data.loss_state    = m.group(3)
        data.loss_zip      = m.group(4)

    # Date of loss — format "08-01-2025"
    m = re.search(r"Date of Loss:\s*(\d{2}-\d{2}-\d{4})", text)
    if m and not data.loss_date:
        data.loss_date = _acuity_date(m.group(1))

    # Cell phone (may differ from claim summary)
    m = re.search(r"Cell Phone:\s*([\d-]+)", text)
    if m and not data.insured_cell:
        data.insured_cell = _digits(m.group(1))


def _parse_policy_summary(text: str, data: ClaimData) -> None:
    """
    Parse Acuity Policy Summary PDF.
    Fills policy effective/expiration dates.
    """
    m = re.search(r"TERM EFFECTIVE:\s*(\d{2}/\d{2}/\d{4})", text)
    if m:
        data.policy_effective = m.group(1)

    m = re.search(r"TERM EXPIRATION:\s*(\d{2}/\d{2}/\d{4})", text)
    if m:
        data.policy_expiration = m.group(1)


def _parse_email_body(body: str, data: ClaimData) -> None:
    """Extract assigned adjuster name from email body."""
    # Email typically starts "Alan," or "Alan Mahurin," — grab the addressee
    m = re.match(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?),", body.strip())
    if m:
        # This is just the first name or full name in the salutation
        # Map against adjusters.json happens later in resolve_adjuster_id
        data.assigned_adjuster_name = m.group(1)


def extract_claim_fields(email_body: str, pdfs: dict[str, bytes]) -> ClaimData:
    """Parse Acuity Insurance PDFs + email body into ClaimData."""
    data = ClaimData()

    if "claim_summary" in pdfs:
        _parse_claim_summary(_pdf_text(pdfs["claim_summary"]), data)

    if "loss_notice" in pdfs:
        _parse_loss_notice(_pdf_text(pdfs["loss_notice"]), data)

    if "policy_summary" in pdfs:
        _parse_policy_summary(_pdf_text(pdfs["policy_summary"]), data)

    _parse_email_body(email_body, data)

    return data


# ── Phase 3: Authentication ────────────────────────────────────────────────────

def get_totp_code() -> str:
    """Generate TOTP, waiting if too close to window boundary (< 5s remaining)."""
    secret = os.environ["FILETRAC_TOTP_SECRET"]
    totp   = pyotp.TOTP(secret)
    time_remaining = 30 - (int(time.time()) % 30)
    if time_remaining < 5:
        time.sleep(time_remaining + 1)
    return totp.now()


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent":      "Mozilla/5.0 (compatible; CatPro-Automation/1.0)",
        "Accept":          "text/html,application/xhtml+xml,*/*",
        "Accept-Language": "en-US,en;q=0.5",
    })
    return session


def cognito_login() -> tuple[str, str]:
    """
    Authenticate via AWS Cognito SRP + TOTP MFA.
    Returns (access_token, evolve_user_id).

    Auth flow discovered via network interception (2026-03-31):
      1. InitiateAuth (USER_SRP_AUTH) → PASSWORD_VERIFIER challenge
      2. RespondToAuthChallenge (PASSWORD_VERIFIER) → SOFTWARE_TOKEN_MFA challenge
      3. RespondToAuthChallenge (SOFTWARE_TOKEN_MFA + TOTP code) → AuthenticationResult
    """
    u = Cognito(
        user_pool_id=COGNITO_USER_POOL_ID,
        client_id=COGNITO_CLIENT_ID,
        username=os.environ["FILETRAC_EMAIL"],
    )
    u.authenticate(password=os.environ["FILETRAC_PASSWORD"])

    # If MFA is required, pycognito raises an MFAChallengeException.
    # We catch it and respond with the TOTP code.
    # However pycognito >= 0.4 handles SOFTWARE_TOKEN_MFA automatically
    # via the totp_token parameter — try that first.
    return u.access_token, u.id_token


def cognito_login_with_mfa() -> tuple[str, str]:
    """
    Full Cognito SRP + SOFTWARE_TOKEN_MFA login using pycognito.
    Returns (access_token, cognito_user_sub).
    """
    import botocore
    from pycognito.exceptions import SoftwareTokenMFAChallengeException

    u = Cognito(
        user_pool_id=COGNITO_USER_POOL_ID,
        client_id=COGNITO_CLIENT_ID,
        username=os.environ["FILETRAC_EMAIL"],
    )

    try:
        u.authenticate(password=os.environ["FILETRAC_PASSWORD"])
    except SoftwareTokenMFAChallengeException:
        totp_code = get_totp_code()
        u.respond_to_software_token_mfa_challenge(totp_code)

    return u.access_token, u.id_token


def login(session: requests.Session) -> None:
    """
    Full login: Cognito SRP + TOTP → evolveLogin SSO → cms14.filetrac.net session cookie.

    Discovered flow (network interception 2026-03-31):
      POST https://cms14.filetrac.net/system/evolveLogin.asp
        userId=305873
        evolveUserId=<cognito_user_uuid>  (from IdToken sub claim)
        access_token=<cognito_access_token>
        URL=claimList.asp
      → 302 → claimList.asp, sets ASPSESSIONID* cookie
    """
    access_token, id_token = cognito_login_with_mfa()

    # Extract evolveUserId (sub) from the IdToken JWT payload
    id_payload_b64 = id_token.split(".")[1]
    # Add padding if needed
    id_payload_b64 += "=" * (-len(id_payload_b64) % 4)
    id_payload = json.loads(base64.b64decode(id_payload_b64))
    evolve_user_id = id_payload["sub"]

    resp = session.post(
        EVOLVE_LOGIN_URL,
        data={
            "userId":       FILETRAC_LEGACY_USER_ID,
            "evolveUserId": evolve_user_id,
            "access_token": access_token,
            "URL":          "claimList.asp",
        },
        timeout=TIMEOUT,
        allow_redirects=True,
    )
    resp.raise_for_status()

    # Verify we landed on FileTrac (not redirected back to login)
    if "claimList.asp" not in resp.url and "login" in resp.url.lower():
        raise RuntimeError(f"Login failed — unexpected URL: {resp.url}")

    # Confirm session cookie is set
    if not any("ASPSESSIONID" in k for k in session.cookies.keys()):
        raise RuntimeError("Login failed — no ASPSESSIONID cookie received")


# ── Phase 4: CSRF + Claim Submission ──────────────────────────────────────────

COMPANY_AUTOCOMPLETE_URL = "https://cms14.filetrac.net/system/claimEdit_clientList.asp"


def resolve_company_id(session: requests.Session, company_name: str) -> str:
    """Look up FileTrac numeric company ID via autocomplete. Returns first match or '0'."""
    """
    Look up FileTrac numeric company ID for a given company name via the
    autocomplete endpoint. Returns the first match's ID, or "0" if not found.
    """
    resp = session.get(
        COMPANY_AUTOCOMPLETE_URL,
        params={"mode": "customerCompanies", "tgtCompany": company_name},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    m = re.search(r"<rs id='(\d+)'", resp.text)
    return m.group(1) if m else "0"


def resolve_company_contact(session: requests.Session, company_id: str) -> str:
    """
    Fetch the first contact user ID for a company.
    The customerReps response is a '~'-delimited list of entries; the first entry's
    7th '##'-delimited field is the primary contact user ID.
    Returns '0' if no contacts found.
    """
    resp = session.get(
        COMPANY_AUTOCOMPLETE_URL,
        params={"mode": "customerReps", "companyID": company_id},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    # Response format: header_entry~contact_id##...~contact_id##...
    # Entry 0 is the company header; entries 1+ are contacts whose ID is the first field.
    entries = resp.text.split("~")
    for entry in entries[1:]:
        uid = entry.split("##")[0]
        if uid.isdigit() and uid != "0":
            return uid
    return "0"


def extract_csrf_token(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    tag  = soup.find("input", attrs={"type": "hidden", "name": "pageLayout_CSRtoken"})
    if not tag or not tag.get("value"):
        raise RuntimeError("CSRF token not found in claimAdd.asp — session may be expired")
    return tag["value"]


def resolve_adjuster_id(adjuster_name: str) -> str:
    """
    Map adjuster name → FileTrac user ID via adjusters.json.
    adjusters.json keys are in "Last, First" format.
    Handles: "First Last", "Last, First", or first-name-only inputs.
    Uses case-insensitive word-level matching.
    """
    mapping_path = Path(__file__).parent / "adjusters.json"
    if not mapping_path.exists() or not adjuster_name:
        return "0"

    mapping    = json.loads(mapping_path.read_text())
    name_lower = adjuster_name.strip().lower()
    # Extract individual words from the input name
    input_words = set(name_lower.replace(",", " ").split())

    best_uid   = "0"
    best_score = 0

    for key, uid in mapping.items():
        key_words = set(key.lower().replace(",", " ").split())
        # Score = number of matching words
        score = len(input_words & key_words)
        if score > best_score:
            best_score = score
            best_uid   = str(uid)

    # "302465" = UNASSIGNED in FileTrac dropdown
    return best_uid if best_score > 0 else "302465"


def _parse_select_first_value(html: str, name: str) -> str:
    """Return the first non-placeholder option value from a <select>."""
    soup = BeautifulSoup(html, "html.parser")
    sel  = soup.find("select", attrs={"name": name})
    if not sel:
        return "0"
    for opt in sel.find_all("option"):
        v    = opt.get("value", "")
        text = opt.get_text(strip=True)
        # Skip empty, negative, UNASSIGNED, separator, and "Select" placeholders
        if not v or v in ("-1", "0", "302465"):
            continue
        if "---" in text or "select" in text.lower() or "unassigned" in text.lower():
            continue
        return v
    return "0"


def _parse_hidden(html: str, name: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    tag  = soup.find("input", attrs={"type": "hidden", "name": name})
    return tag["value"] if tag and tag.get("value") else "0"


def _now_time() -> str:
    """Return current time as FileTrac expects: 'H:MM AM/PM'."""
    from datetime import datetime
    return datetime.now().strftime("%-I:%M %p")


class SubmitResult(pydantic.BaseModel):
    """Result of a claim submission attempt."""
    claim_id: str  # "claimID=NNNNNNN", "DRY_RUN", etc.
    claim_fields: dict  # ClaimData as dict
    resolved_ids: dict  # FileTrac IDs resolved during submission
    payload: dict | None = None  # Full form payload (if built)


def submit_claim(session: requests.Session, claim: ClaimData) -> SubmitResult:
    """Submit claim to FileTrac. Returns SubmitResult with claim data and resolved IDs."""

    # GET claim form — extracts CSRF token and default form values
    resp = session.get(CLAIM_FORM_URL, timeout=TIMEOUT)
    resp.raise_for_status()
    html = resp.text

    csrf_token  = extract_csrf_token(html)
    adjuster_id = resolve_adjuster_id(claim.assigned_adjuster_name or "")
    company_id  = resolve_company_id(session, claim.client_company_name or "")

    # Single customerReps call — get both contact_id and company_email
    contact_id    = "0"
    company_email = ""
    if company_id != "0":
        reps_resp = session.get(COMPANY_AUTOCOMPLETE_URL,
                                params={"mode": "customerReps", "companyID": company_id},
                                timeout=TIMEOUT)
        reps_text = reps_resp.text
        # Header: ##/##CompanyName##email##...  → company email
        mh = re.match(r"##/##[^#]*##([^#@\s]+@[^#\s]+)##", reps_text)
        if mh:
            company_email = mh.group(1)
        # Contacts: header~contact_id##...  → first contact user ID
        entries = reps_text.split("~")
        for entry in entries[1:]:
            uid = entry.split("##")[0]
            if uid.isdigit() and uid != "0":
                contact_id = uid
                break

    # ABID (branch ID) is populated by companyID_onchange — fetch it via the branches endpoint
    abid = "0"
    if company_id != "0":
        r = session.get(COMPANY_AUTOCOMPLETE_URL,
                        params={"mode": "customerBranches", "companyID": company_id},
                        timeout=TIMEOUT)
        m = re.match(r"(\d+)##", r.text)
        abid = m.group(1) if m else "0"

    # ACmgrID — first real manager option in the form select
    acmgr_id = _parse_select_first_value(html, "ACmgrID")

    resolved_ids = {
        "company_id": company_id,
        "contact_id": contact_id,
        "branch_id": abid,
        "adjuster_id": adjuster_id,
        "manager_id": acmgr_id,
        "csrf_token": csrf_token,
    }

    now = _now_time()

    # Standard acknowledgement letter text (same as browser default)
    letter_text = (
        "We acknowledge receipt of the above referenced claim. I have been assigned to this claim. "
        "Please direct all correspondence to me. If you should have any further information, special "
        "instructions, or any questions, please contact our office immediately. We wish to thank you "
        "for this assignment, and we value your Business."
    )

    payload = {
        # ── CSRF + core hidden fields ──────────────────────────────────────────
        "pageLayout_CSRtoken":    csrf_token,
        "newUserId":              "",
        "ContactLineCount":       "1",
        "LatDataVal":             "",
        "LongDataVal":            "",
        "stormID":                "-1",
        # ── Client (insurer) ───────────────────────────────────────────────────
        "companyIDTxt":           claim.client_company_name or "",
        "companyID":              company_id,
        "companyUserID":          contact_id,
        "companyUserEMail":       "-1",
        "companyUserEmail_display": "NONE",
        "ABID":                   abid,
        "asgnID":                 "0",
        "claimFileID":            "##AUTO",
        "prefixID":               "##AUTO",
        "claimFileID2":           "",
        "claimCompanyID2":        "0",
        "companyFileID":          claim.client_claim_number or "",
        "inLitigationStatus":     "",
        "claimDateReceived":      date.today().strftime("%-m/%-d/%Y"),
        "ddlClipping":            "-1",
        "AUTO_claimInstructions": "",
        "claimInstructions":      "",
        "claimScheduleID":        "0",
        "claimBudget":            "",
        # ── Insured ────────────────────────────────────────────────────────────
        "insuredFName":           claim.insured_first_name   or "",
        "insuredSex":             "",
        "insuredDOB":             "",
        "insuredOccupation":      "",
        "insuredSSN":             "",
        "insuredLName":           claim.insured_last_name    or "",
        "insuredCompany":         "",
        "insuredEMail":           claim.insured_email        or "",
        "insuredPolicyNum":       claim.policy_number        or "",
        "insuredaltPolicyNum":    "",
        "PolicyType":             "",
        "insuredPolicyType":      "",
        "insuredPolicyStart":     claim.policy_effective     or "",
        "insuredPolicyEnd":       claim.policy_expiration    or "",
        "insuredPolicyRenewal":   "",
        "insuredLoanNum":         "",
        "insuredPhone":           claim.insured_phone        or "",
        "insuredPhone2":          "",
        "insuredPhone3":          claim.insured_cell         or "",
        "insuredAddr1":           claim.insured_address1     or "",
        "insuredAddr2":           "",
        "insuredCity":            claim.insured_city         or "",
        "insuredState":           claim.insured_state        or "",
        "insuredZIP":             claim.insured_zip          or "",
        "insuredCountry":         "",
        "insuredMortgagee":       "",
        "claimRORDate":           "",
        "insuredDriversLicense":  "",
        "insuredOHIP":            "",
        "secondaryInsuredFName":  claim.secondary_insured_first or "",
        "secondaryInsuredLName":  claim.secondary_insured_last  or "",
        # ── Doctor (blank) ─────────────────────────────────────────────────────
        "docFName": "", "docLName": "", "docPhone": "",
        "docAddr1": "", "docAddr2": "", "docCity": "", "docState": " ", "docZIP": "",
        "remLenD":  "1000",
        "docDiagnosis": "", "docSurgery": "",
        # ── Attorney (blank) ───────────────────────────────────────────────────
        "attorneyTypeID":  "3",
        "attorneyFName": "", "attorneyLName": "", "attorneyCompany": "",
        "attorneyPhone1": "", "attorneyPhone2": "", "attorneyFax": "",
        "attorneyEMail": "",
        "attorneyAddr1": "", "attorneyAddr2": "", "attorneyCity": "",
        "attorneyState": " ", "attorneyZIP": "", "attorneyCountry": "",
        # ── Agent ──────────────────────────────────────────────────────────────
        "agentFName": "", "agentLName": "",
        "agentCompany": claim.agent_company  or "",
        "agentCode":    "",
        "agentPhone1":  claim.agent_phone    or "",
        "agentPhone2":  "",
        "agentFax":     "",
        "agentEMail":   claim.agent_email    or "",
        "agentAddr1":   claim.agent_address1 or "",
        "agentAddr2":   "",
        "agentCity":    claim.agent_city     or "",
        "agentState":   claim.agent_state    or " ",
        "agentZIP":     claim.agent_zip      or "",
        "agentCountry": "",
        # ── Loss location ──────────────────────────────────────────────────────
        "claimPremiseNumber": "", "claimBuildingNumber": "",
        "lossAddr1":  claim.loss_address1 or "",
        "lossAddr2":  "",
        "lossCity":   claim.loss_city     or "",
        "lossState":  claim.loss_state    or " ",
        "lossZIP":    claim.loss_zip      or "",
        "lossCounty": "", "lossCountry": "",
        "ContingencyAmount": "",
        # ── Claimant (blank) ───────────────────────────────────────────────────
        "claimantFName": "", "claimantLName": "", "claimantCompany": "",
        "claimantDOB": "", "claimantSSN": "", "claimantSex": "",
        "claimantOccupation": "", "claimantMarital": "",
        "claimantDisabilityStart": "", "claimantDisabilityEnd": "",
        "claimantInjury": "", "claimantHICN": "",
        "claimMedicareRequestDate": "",
        "claimantEMail": "", "claimantPhone": "", "claimantPhone1": "",
        "claimantAddr1": "", "claimantAddr2": "", "claimantCity": "",
        "claimantState": " ", "claimantZIP": "", "claimantCountry": "",
        "claimantDriversLicense": "", "claimantOHIP": "",
        # ── Contact line 1 (blank) ─────────────────────────────────────────────
        "ashish":        "1",
        "contactID1":    "0",
        "contactTypeID1":"7",
        "contactCompany1": "", "contactLName1": "", "contactFName1": "",
        "contactAddr11": "", "contactAddr21": "", "contactCity1": "",
        "contactState1": " ", "contactZIP1": "",
        "contactPhone11": "", "contactPhone21": "", "contactEMail1": "",
        "partyPaper":    "0",
        # ── Loss ───────────────────────────────────────────────────────────────
        "lossDate":     claim.loss_date        or "",
        "lossType":     claim.loss_type        or "",
        "lossTypeMisc": "",
        "lossUnit":     "Residential",
        "claimAdjType": "Limited",
        # ── ISO / CAT (blank) ──────────────────────────────────────────────────
        "claimISO_LOBOLD": "", "claimISO_LOB": "",
        "claimISO_codeOLD": "", "claimISO_code": "",
        "claimISO_causeOLD": "", "claimISO_cause": "",
        "claimPercentCededOLD": "", "claimPercentCeded": "",
        "LABEL_ddlcauseoflossTEXT": "RISK Code",
        "ddlcauseoflossTEXT": "", "ddlcauseofloss": "",
        "claimCAT_select": "", "claimCAT": "",
        # ── Adjuster / manager ─────────────────────────────────────────────────
        "ACmgrID":          acmgr_id,
        "tempSupervisorID": "0",
        "ACsupervisorID":   "302465",
        "reviewerID":       "302465",
        "ACuserID_inputType": "SELECT",
        "ACuserID":         adjuster_id,
        "txtMaxLoad":       "",
        "adjNote":          "",
        # ── Description / dates / times ────────────────────────────────────────
        "remLen12":                     "1000",
        "lossDescription":              claim.loss_description or "",
        "claimDateContact":             "",
        "claimTimeContact":             now,
        "claimDateInspection2":         "",
        "claimTimeInspection2":         now,
        "claimDateInspection":          "",
        "claimTimeInspection":          now,
        "MilestoneDER":                 "0",
        "LABEL_claimDateReviewed":      "",
        "claimDateReviewed":            "",
        "claimTimeReviewed":            now,
        "LABEL_claimDatePayment_recommended": "",
        "claimDatePayment_recommended": "",
        "claimTimePayment_recommended": now,
        # ── Vehicle (blank) ────────────────────────────────────────────────────
        "claimVIN": "",
        # ── Coverage / financial ───────────────────────────────────────────────
        "claimDeductable": "", "claimDeductiblePercent": "",
        "claimWindDeductable": "", "claimWindDeductiblePercent": "",
        "claimPremium": "", "claimTIV": "", "claimOccurrenceLimit": "",
        "claimCoverageA_typeID": "0", "claimCoverageA": "",
        "claimCoverageB_typeID": "0", "claimCoverageB": "",
        "claimCoverageC_typeID": "0", "claimCoverageC": "",
        "claimCoverageD_typeID": "0", "claimCoverageD": "",
        "claimEndorsements": "",
        "claimCoverageE_deductible": "", "claimCoverageF_deductible": "",
        # ── Auto (blank) ───────────────────────────────────────────────────────
        "claimAutoYear": "", "claimAutoMake": "", "claimAutoModel": "",
        "claimAutoVIN": "", "claimAutoDamages": "", "claimAutoCoverage": "",
        "claimAutoDeductible": "", "claimAutoLocation": "",
        "OLD_claimAutoFault": "", "claimAutoFault": "",
        "OLD_claimAutoWeather": "", "claimAutoWeather": "",
        "OLD_claimAutoRoad": "", "claimAutoRoad": "",
        # ── Misc ───────────────────────────────────────────────────────────────
        "tencoCC": "",
        "claimReasonCodeID": "0",
        "remLen2": "1000",
        # ── Letter / notification ──────────────────────────────────────────────
        "chkEMailLetter":  "1",
        "chkPDFLetter":    "1",
        "chkPrintLetter":  "0",
        "tennessee":       "0",
        "ackALERT":        "0",
        "ddlClipping":     "-1",
        "letterText":      letter_text,
        "acknowledgeEMail": "",
        "companyEMail":    company_email,
        "FLOODnotice":     "0",
        "LossNoticeEMail": "",
        "workQID":         "0",
    }

    # Dry-run: stop before the billable POST
    if os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes"):
        print("[DRY RUN] Skipping claim submission POST — payload ready:")
        print(f"  Insured: {claim.insured_first_name} {claim.insured_last_name}")
        print(f"  Policy:  {claim.policy_number}")
        print(f"  Loss:    {claim.loss_date} — {claim.loss_type}")
        print(f"  Client:  {claim.client_company_name} #{claim.client_claim_number}")
        print(f"  Adjuster ID: {adjuster_id} | Company ID: {company_id}")
        print(f"  CSRF token: {csrf_token[:20]}...")
        return SubmitResult(
            claim_id="DRY_RUN",
            claim_fields=claim.model_dump(),
            resolved_ids=resolved_ids,
            payload=payload,
        )

    resp = session.post(CLAIM_SAVE_URL, data=payload, timeout=TIMEOUT, allow_redirects=True)
    resp.raise_for_status()

    def _result(cid: str) -> SubmitResult:
        return SubmitResult(
            claim_id=cid,
            claim_fields=claim.model_dump(),
            resolved_ids=resolved_ids,
            payload=payload,
        )

    # Success: response body contains <!-- claimID = [NNNNNNN] -->
    m = re.search(r"<!--\s*claimID\s*=\s*\[(\d+)\]", resp.text)
    if m:
        return _result(f"claimID={m.group(1)}")

    # Also check redirect URL (claimList.asp?searchTgt=...)
    m = re.search(r"searchTgt=(\d+)", resp.url)
    if m:
        return _result(f"claimID={m.group(1)}")

    # Try to extract file number from response body (format: YY-NNNNN, e.g. "26-00123")
    match = re.search(r"\b(2[0-9]-\d{4,6})\b", resp.text)
    if match:
        return _result(match.group(1))

    # Failure: check for validation errors in response
    alerts = re.findall(r"alert\(['\"](.+?)['\"]\)", resp.text)
    real_errors = [a for a in alerts if any(w in a.lower() for w in ['required', 'select a valid', 'please select', 'cannot'])]
    if real_errors:
        raise RuntimeError(f"Claim submission failed: {'; '.join(real_errors[:3])}")

    return _result(f"submitted (final URL: {resp.url})")


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

    print("[3/4] Authenticating to FileTrac...")
    session = build_session()
    login(session)
    print("      Authenticated.")

    print("[4/4] Submitting claim...")
    result = submit_claim(session, claim)
    print(f"      Claim created: {result.claim_id}")


if __name__ == "__main__":
    main()
