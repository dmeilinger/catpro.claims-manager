#!/usr/bin/env python3.13
"""
ft_query.py — Query FileTrac claim data without re-authenticating.

Manages the session automatically: checks saved session, logs in (one TOTP) only if expired.

Usage:
    python3.13 scripts/ft_query.py list                          # all open claims
    python3.13 scripts/ft_query.py list --status BOTH            # open + closed
    python3.13 scripts/ft_query.py list --status CLOSED
    python3.13 scripts/ft_query.py list --group-by adjuster      # count by adjuster
    python3.13 scripts/ft_query.py list --group-by status        # count by file status
    python3.13 scripts/ft_query.py list --adjuster "Brian Lara"  # claims for one adjuster
    python3.13 scripts/ft_query.py list --file-status "Pending Inspection"
    python3.13 scripts/ft_query.py list --company acuity
    python3.13 scripts/ft_query.py list --loss-type Hail
    python3.13 scripts/ft_query.py list --overdue                # past due date
    python3.13 scripts/ft_query.py claim 26-10113                # one claim's detail
    python3.13 scripts/ft_query.py summary                       # full breakdown
"""

import argparse
import re
import subprocess
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bs4 import BeautifulSoup

from scripts.ft_session import COOKIE_FILE, check_session, load_session, save_session

CLAIM_LIST_URL = "https://cms14.filetrac.net/system/claimList.asp"
CLAIM_EDIT_URL = "https://cms14.filetrac.net/system/claimEdit.asp"

# Known company name aliases → FileTrac companyID
COMPANY_IDS = {
    "acuity": "175475",
    "acuity insurance": "175475",
    "auto-owners": "70194",
    "auto owners": "70194",
    "homeowners of america": "70594",
    "allstate": "70485",
    "srm": "70485",
    "test": "143898",
    "test company": "143898",
}

# Known branch aliases → FileTrac ABID
BRANCH_IDS = {
    "main": "1823",
    "main branch": "1823",
    "allstate": "2202",
    "srm": "2202",
    "test": "2529",
}


# ── Session management ────────────────────────────────────────────────────────

def ensure_session():
    """Return an authenticated requests.Session, logging in only if needed."""
    if COOKIE_FILE.exists():
        session = load_session()
        if check_session(session):
            return session
        print("[ft_query] Session expired — re-authenticating (one TOTP)...", file=sys.stderr)
    else:
        print("[ft_query] No saved session — authenticating (one TOTP)...", file=sys.stderr)

    # Import here to avoid loading auth deps on every run
    from app.services.filetrac_auth import build_session, login
    session = build_session()
    login(session)
    save_session(session)
    return session


# ── HTML parsing ──────────────────────────────────────────────────────────────

def _parse_claims(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    grid = next((t for t in soup.find_all("table") if t.find("thead")), None)
    if not grid:
        return []
    rows = grid.find("tbody").find_all("tr") if grid.find("tbody") else grid.find_all("tr")[1:]
    claims = []
    for row in rows:
        cells = [td.get_text(strip=True) for td in row.find_all("td")]
        if not cells or "No Claims" in cells[0]:
            continue
        links = [a.get("href", "") for a in row.find_all("a") if "claimEdit.asp?claimID=" in a.get("href", "")]
        m = re.search(r"claimID=(\d+)", links[0]) if links else None
        due_m = re.search(r"Due:\s*(.+)", cells[5]) if len(cells) > 5 else None
        claims.append({
            "claim_id": m.group(1) if m else "",
            "file":     re.sub(r"UPLOAD.*", "", cells[0]).strip(),
            "claim_num": re.sub(r"Doc\..*", "", cells[1]).strip() if len(cells) > 1 else "",
            "received": cells[2] if len(cells) > 2 else "",
            "insured":  re.sub(r"CONTACTS.*", "", cells[3]).strip() if len(cells) > 3 else "",
            "client":   cells[4].replace("\xa0", " ") if len(cells) > 4 else "",
            "status":   re.sub(r"Due:.*", "", cells[5]).strip() if len(cells) > 5 else "",
            "due":      due_m.group(1).strip() if due_m else "",
            "adjuster": cells[7] if len(cells) > 7 else "",
        })
    return claims


def _fetch_claims(session, *, status="OPEN", search_type="*", search_tgt="",
                  file_status="", company_id="", branch_id="", loss_type="",
                  loss_unit="", manager_id="", limit=100) -> list[dict]:
    params = {
        "searchType": search_type,
        "searchTgt":  search_tgt,
        "multiStatus": status,
        "maxLINES": str(limit),
        "btnSearch": "Search",
    }
    if file_status:  params["multiFileStatus"] = file_status
    if company_id:   params["multiCompany"]    = company_id
    if branch_id:    params["multiABID"]       = branch_id
    if loss_type:    params["multilossType"]   = loss_type
    if loss_unit:    params["multilossUnit"]   = loss_unit
    if manager_id:   params["multiMgrID"]      = manager_id

    resp = session.post(CLAIM_LIST_URL, data=params, timeout=30)
    resp.raise_for_status()
    return _parse_claims(resp.text)


# ── Output formatters ─────────────────────────────────────────────────────────

def _print_table(claims: list[dict]) -> None:
    if not claims:
        print("No claims found.")
        return
    print(f"{'File #':<12} {'Claim #':<12} {'Received':<11} {'Insured':<22} {'Status':<30} {'Due':<12} {'Adjuster'}")
    print("-" * 115)
    for c in claims:
        print(f"{c['file']:<12} {c['claim_num']:<12} {c['received']:<11} {c['insured'][:21]:<22} {c['status'][:29]:<30} {c['due']:<12} {c['adjuster']}")
    print(f"\nTotal: {len(claims)}")


def _print_group(claims: list[dict], key: str) -> None:
    if not claims:
        print("No claims found.")
        return
    counter = Counter(c[key] for c in claims)
    print(f"{'Group':<35} Count")
    print("-" * 45)
    for label, count in sorted(counter.items(), key=lambda x: -x[1]):
        print(f"{label:<35} {count}")
    print(f"\nTotal: {len(claims)}")


def _is_overdue(due: str) -> bool:
    if not due:
        return False
    try:
        parts = due.strip().split("/")
        if len(parts) == 3:
            m, d, y = int(parts[0]), int(parts[1]), int(parts[2])
            return date(y, m, d) < date.today()
    except (ValueError, IndexError):
        pass
    return False


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_list(args) -> None:
    session = ensure_session()

    company_id = COMPANY_IDS.get(args.company.lower(), args.company) if args.company else ""
    branch_id  = BRANCH_IDS.get(args.branch.lower(), args.branch) if args.branch else ""

    # Adjuster search uses a different searchType
    search_type = "*"
    search_tgt  = ""
    if args.adjuster:
        search_type = "adjFullName"
        search_tgt  = args.adjuster

    claims = _fetch_claims(
        session,
        status=args.status,
        search_type=search_type,
        search_tgt=search_tgt,
        file_status=args.file_status or "",
        company_id=company_id,
        branch_id=branch_id,
        loss_type=args.loss_type or "",
        loss_unit=args.loss_unit or "",
        limit=args.limit,
    )

    if args.overdue:
        claims = [c for c in claims if _is_overdue(c["due"])]

    if args.group_by == "adjuster":
        _print_group(claims, "adjuster")
    elif args.group_by == "status":
        _print_group(claims, "status")
    elif args.group_by == "client":
        _print_group(claims, "client")
    else:
        _print_table(claims)


def cmd_claim(args) -> None:
    session = ensure_session()
    file_num = args.file_number

    # Search by exact file number to get the claim ID, then fetch detail
    claims = _fetch_claims(session, status="BOTH", search_type="claimFileID", search_tgt=file_num)
    if not claims:
        print(f"Claim {file_num} not found.")
        return

    c = claims[0]
    print(f"File #:     {c['file']}")
    print(f"Claim #:    {c['claim_num']}")
    print(f"Claim ID:   {c['claim_id']}")
    print(f"Received:   {c['received']}")
    print(f"Insured:    {c['insured']}")
    print(f"Client:     {c['client']}")
    print(f"Status:     {c['status']}")
    print(f"Due:        {c['due']}")
    print(f"Adjuster:   {c['adjuster']}")
    if c["due"] and _is_overdue(c["due"]):
        print("⚠  OVERDUE")


def cmd_summary(args) -> None:
    session = ensure_session()
    claims = _fetch_claims(session, status="OPEN", limit=100)

    print(f"=== Open Claims Summary — {date.today()} ===\n")
    print(f"Total open: {len(claims)}\n")

    print("By Adjuster:")
    _print_group(claims, "adjuster")
    print()

    print("By File Status:")
    _print_group(claims, "status")
    print()

    overdue = [c for c in claims if _is_overdue(c["due"])]
    print(f"Overdue: {len(overdue)}")
    for c in overdue:
        print(f"  {c['file']}  {c['insured'][:20]:<20}  due {c['due']}  ({c['adjuster']})")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Query FileTrac claim data")
    sub = parser.add_subparsers(dest="command", required=True)

    # list
    p_list = sub.add_parser("list", help="List claims with optional filters")
    p_list.add_argument("--status", default="OPEN", choices=["OPEN", "CLOSED", "BOTH"])
    p_list.add_argument("--adjuster",    help="Filter by adjuster name")
    p_list.add_argument("--file-status", help="Filter by file workflow status")
    p_list.add_argument("--company",     help="Filter by company name or ID (e.g. 'acuity')")
    p_list.add_argument("--branch",      help="Filter by branch name or ID (e.g. 'main', 'test')")
    p_list.add_argument("--loss-type",   help="Filter by loss type (e.g. 'Hail', 'Wind')")
    p_list.add_argument("--loss-unit",   help="Filter by unit: Residential | Commercial | Ladder Assist")
    p_list.add_argument("--overdue",     action="store_true", help="Only show overdue claims")
    p_list.add_argument("--group-by",    choices=["adjuster", "status", "client"], help="Group and count instead of listing")
    p_list.add_argument("--limit",       type=int, default=100)

    # claim
    p_claim = sub.add_parser("claim", help="Show detail for one claim")
    p_claim.add_argument("file_number", help="File number e.g. 26-10113")

    # summary
    sub.add_parser("summary", help="Full open-claims breakdown by adjuster and status")

    args = parser.parse_args()
    if args.command == "list":
        cmd_list(args)
    elif args.command == "claim":
        cmd_claim(args)
    elif args.command == "summary":
        cmd_summary(args)


if __name__ == "__main__":
    main()
