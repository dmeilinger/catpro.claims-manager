"""FileTrac claim submission — CSRF, ID resolution, and form POST."""

import json
import re
from datetime import date, datetime
from pathlib import Path

import pydantic
import requests
from bs4 import BeautifulSoup

from app.services.filetrac_auth import FILETRAC_LEGACY_USER_ID, FILETRAC_LEGACY_SYSTEM_ID, TIMEOUT  # noqa: F401
from app.services.pdf_extractor import ClaimData

# ── Constants ──────────────────────────────────────────────────────────────────

COMPANY_AUTOCOMPLETE_URL = "https://cms14.filetrac.net/system/claimEdit_clientList.asp"
CLAIM_FORM_URL           = "https://cms14.filetrac.net/system/claimAdd.asp"
CLAIM_SAVE_URL           = "https://cms14.filetrac.net/system/claimSave.asp?newFlag=1&anotherFlag=0"
CLAIM_EDIT_URL           = "https://cms14.filetrac.net/system/claimEdit.asp"
CLAIM_UPDATE_URL         = "https://cms14.filetrac.net/system/claimSave.asp?newFlag=0&anotherFlag=0"


# ── ID resolution helpers ──────────────────────────────────────────────────────

def resolve_company_id(session: requests.Session, company_name: str) -> str:
    """Look up FileTrac numeric company ID via autocomplete. Returns first match or '0'."""
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
    return datetime.now().strftime("%-I:%M %p")


# ── Submission ─────────────────────────────────────────────────────────────────

class SubmitResult(pydantic.BaseModel):
    """Result of a claim submission attempt."""
    claim_id: str  # "claimID=NNNNNNN", "DRY_RUN", etc.
    claim_fields: dict  # ClaimData as dict
    resolved_ids: dict  # FileTrac IDs resolved during submission
    payload: dict | None = None  # Full form payload (if built)


def submit_claim(
    session: requests.Session,
    claim: ClaimData,
    *,
    dry_run: bool = False,
    test_mode: bool = False,
    test_adjuster_id: str = "342436",
    test_branch_id: str = "2529",
    existing_claim_id: str = "",
    test_company_id: str = "143898",   # "Test Company" in FileTrac
) -> SubmitResult:
    """Submit claim to FileTrac. Returns SubmitResult with claim data and resolved IDs.

    existing_claim_id: if set, UPDATE that claim (claimSave.asp?newFlag=0) instead of
    creating a new one. Use a permanent "sandbox" claim ID during testing to avoid
    incurring per-claim charges.
    """
    update_mode = bool(existing_claim_id)

    # GET claim form — extracts CSRF token and default form values.
    # For updates, use the edit page for the specific claim so we get the right CSRF.
    if update_mode:
        resp = session.get(CLAIM_EDIT_URL, params={"claimID": existing_claim_id}, timeout=TIMEOUT)
    else:
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

    # Test mode: override ALL IDs with test account values — no real company/contact/email
    if test_mode:
        adjuster_id   = test_adjuster_id
        abid          = test_branch_id
        company_id    = test_company_id    # Test Company — never Acuity or any real insurer
        contact_id    = "0"               # no real contact
        company_email = ""                # no real email — prevents acknowledgement emails
        resolved_ids["adjuster_id"] = adjuster_id
        resolved_ids["branch_id"]   = abid
        resolved_ids["company_id"]  = company_id
        resolved_ids["contact_id"]  = contact_id
        print(f"[TEST MODE] company={company_id}, adjuster={adjuster_id}, branch={abid}, contact=0, email=off")

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
        "claimFileID":            existing_claim_id if update_mode else "##AUTO",
        "prefixID":               "" if update_mode else "##AUTO",
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
        "chkEMailLetter":  "0" if test_mode else "1",
        "chkPDFLetter":    "0" if test_mode else "1",
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
    if dry_run:
        mode_label = f"UPDATE claimID={existing_claim_id}" if update_mode else "CREATE new claim"
        print(f"[DRY RUN] Skipping claim submission POST ({mode_label}) — payload ready:")
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

    save_url = CLAIM_UPDATE_URL if update_mode else CLAIM_SAVE_URL
    resp = session.post(save_url, data=payload, timeout=TIMEOUT, allow_redirects=True)
    resp.raise_for_status()

    def _result(cid: str) -> SubmitResult:
        return SubmitResult(
            claim_id=cid,
            claim_fields=claim.model_dump(),
            resolved_ids=resolved_ids,
            payload=payload,
        )

    # Update mode: no new claimID is issued — confirm with the known ID
    if update_mode:
        alerts = re.findall(r"alert\(['\"](.+?)['\"]\)", resp.text)
        real_errors = [a for a in alerts if any(w in a.lower() for w in ['required', 'select a valid', 'please select', 'cannot'])]
        if real_errors:
            raise RuntimeError(f"Claim update failed: {'; '.join(real_errors[:3])}")
        return _result(f"updated claimID={existing_claim_id}")

    # Create mode: response body contains <!-- claimID = [NNNNNNN] -->
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
