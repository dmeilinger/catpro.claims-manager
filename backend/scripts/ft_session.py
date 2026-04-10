#!/usr/bin/env python3.13
"""
Manage a reusable FileTrac session cookie.

Usage:
    python3.13 scripts/ft_session.py login        # authenticate once, save cookie
    python3.13 scripts/ft_session.py check        # verify saved session is still alive
    python3.13 scripts/ft_session.py get <url>    # GET a FileTrac URL using saved session

The cookie is stored in data/ft_session.json. Re-run 'login' only when it expires.
"""

import json
import sys
from pathlib import Path

import requests

COOKIE_FILE = Path(__file__).resolve().parents[2] / "data" / "ft_session.json"
CHECK_URL   = "https://cms14.filetrac.net/system/claimList.asp"


def save_session(session: requests.Session) -> None:
    cookies = {c.name: c.value for c in session.cookies}
    COOKIE_FILE.write_text(json.dumps(cookies, indent=2))
    print(f"Session saved to {COOKIE_FILE}")
    for name, val in cookies.items():
        print(f"  {name} = {val[:20]}...")


def load_session() -> requests.Session:
    if not COOKIE_FILE.exists():
        print("No saved session — run: python3.13 scripts/ft_session.py login", file=sys.stderr)
        sys.exit(1)
    cookies = json.loads(COOKIE_FILE.read_text())
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    for name, val in cookies.items():
        session.cookies.set(name, val, domain="cms14.filetrac.net")
    return session


def check_session(session: requests.Session) -> bool:
    resp = session.get(CHECK_URL, timeout=15, allow_redirects=False)
    # FileTrac redirects to login page if session is expired
    if resp.status_code in (301, 302):
        loc = resp.headers.get("Location", "")
        if "login" in loc.lower() or "evolve" in loc.lower():
            return False
    return resp.status_code == 200


def cmd_login() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.services.filetrac_auth import build_session, login as ft_login
    session = build_session()
    ft_login(session)
    save_session(session)


def cmd_check() -> None:
    session = load_session()
    alive = check_session(session)
    print(f"Session {'ALIVE' if alive else 'EXPIRED — re-run login'}")


def cmd_get(url: str) -> None:
    import re
    session = load_session()
    resp = session.get(url, timeout=30)
    print(f"Status: {resp.status_code} | URL: {resp.url}")
    # Print hrefs and any claim file numbers found
    links = sorted(set(re.findall(r'href=["\']([^"\']{5,})["\']', resp.text)))
    file_nums = sorted(set(re.findall(r'\b2[0-9]-\d{4,6}\b', resp.text)))
    js_ids = sorted(set(re.findall(r"[Cc]laim(?:FileID|Edit)[^'\"]*?['\"]?=\W*?(\d{6,})", resp.text)))
    if file_nums:
        print(f"\nFile numbers: {file_nums}")
    if js_ids:
        print(f"Numeric IDs near claim links: {js_ids[:20]}")
    if links:
        print("\nHrefs:")
        for l in links[:40]:
            print(f"  {l}")
    # Also dump a raw slice around the first file number for context
    if file_nums:
        idx = resp.text.find(file_nums[-1])  # newest
        if idx >= 0:
            print(f"\n--- Context around {file_nums[-1]} ---")
            print(resp.text[max(0, idx-300):idx+400])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "login":
        cmd_login()
    elif cmd == "check":
        cmd_check()
    elif cmd == "get" and len(sys.argv) > 2:
        cmd_get(sys.argv[2])
    else:
        print(__doc__)
