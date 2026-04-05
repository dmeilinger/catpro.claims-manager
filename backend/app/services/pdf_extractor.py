"""Acuity Insurance PDF parsing — extracts claim fields from PDF attachments."""

import io
import re

import pdfplumber
import pydantic


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
