"""FileTrac authentication — AWS Cognito SRP + TOTP + evolveLogin SSO."""

import base64
import json
import time

import pyotp
import requests
from pycognito import Cognito

from app.config import get_settings

# ── Constants ──────────────────────────────────────────────────────────────────

COGNITO_USER_POOL_ID = "us-east-1_BOlb3igmv"
COGNITO_CLIENT_ID    = "1frtspmi2af7o8hqtfsfebrc6"
# FileTrac legacy IDs for CatPro (discovered via network interception)
FILETRAC_LEGACY_USER_ID   = "305873"
FILETRAC_LEGACY_SYSTEM_ID = "405"

EVOLVE_LOGIN_URL = "https://cms14.filetrac.net/system/evolveLogin.asp"

TIMEOUT = (10, 30)


# ── Auth functions ─────────────────────────────────────────────────────────────

def get_totp_code() -> str:
    """Generate TOTP, waiting if too close to window boundary (< 5s remaining)."""
    secret = get_settings().filetrac_totp_secret.get_secret_value()
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
    s = get_settings()
    u = Cognito(
        user_pool_id=COGNITO_USER_POOL_ID,
        client_id=COGNITO_CLIENT_ID,
        username=s.filetrac_email,
    )
    u.authenticate(password=s.filetrac_password.get_secret_value())

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
    import botocore  # noqa: F401
    from pycognito.exceptions import SoftwareTokenMFAChallengeException

    s = get_settings()
    u = Cognito(
        user_pool_id=COGNITO_USER_POOL_ID,
        client_id=COGNITO_CLIENT_ID,
        username=s.filetrac_email,
    )

    try:
        u.authenticate(password=s.filetrac_password.get_secret_value())
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

    if not any(c.name.startswith("ASPSESSIONID") for c in session.cookies):
        raise RuntimeError(
            f"evolveLogin did not set ASPSESSIONID cookie — final URL: {resp.url}"
        )
