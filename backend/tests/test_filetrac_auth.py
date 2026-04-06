"""Tests for filetrac_auth.py — credential resolution and auth flow.

Coverage focus: the prior implementation used os.environ["FILETRAC_*"] directly,
which caused KeyError when the process hadn't loaded .env via load_dotenv().
These tests verify that all credential access goes through get_settings() so
pydantic-settings reads the .env file regardless of whether os.environ is populated.
"""

import base64
import json
import os
from unittest.mock import MagicMock, patch

import pyotp
import pytest
from pydantic import SecretStr


# ── Test helpers ───────────────────────────────────────────────────────────────

_TEST_TOTP_SECRET = "JBSWY3DPEHPK3PXP"  # Standard RFC 6238 test vector (base32)
_TEST_EMAIL = "test@catpro.com"
_TEST_PASSWORD = "test-password-123"


def _make_id_token(sub: str = "cognito-sub-uuid-1234") -> str:
    """Build a minimal fake JWT id_token containing the given sub claim."""
    header = base64.urlsafe_b64encode(b'{"alg":"HS256"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(json.dumps({"sub": sub}).encode()).rstrip(b"=").decode()
    return f"{header}.{payload}.fakesig"


def _make_mock_settings(
    email: str = _TEST_EMAIL,
    password: str = _TEST_PASSWORD,
    totp_secret: str = _TEST_TOTP_SECRET,
) -> MagicMock:
    """Return a mock settings object with the given FileTrac credentials."""
    s = MagicMock()
    s.filetrac_email = email
    s.filetrac_password = SecretStr(password)
    s.filetrac_totp_secret = SecretStr(totp_secret)
    return s


class _EnvCleaned:
    """Context manager: temporarily removes FILETRAC_* vars from os.environ.

    Simulates a process that loaded credentials only via pydantic-settings
    (i.e. load_dotenv was NOT called and the env vars are not in os.environ).
    This is the scenario that caused KeyError before the fix.
    """

    _KEYS = ("FILETRAC_EMAIL", "FILETRAC_PASSWORD", "FILETRAC_TOTP_SECRET")

    def __enter__(self):
        self._saved = {k: os.environ.pop(k) for k in self._KEYS if k in os.environ}
        return self

    def __exit__(self, *args):
        os.environ.update(self._saved)


# ── get_totp_code ──────────────────────────────────────────────────────────────

class TestGetTotpCode:
    """get_totp_code() must read the secret from get_settings(), not os.environ."""

    def test_returns_six_digit_string(self):
        with patch("app.services.filetrac_auth.get_settings", return_value=_make_mock_settings()):
            from app.services.filetrac_auth import get_totp_code
            code = get_totp_code()
        assert code.isdigit(), f"Expected all-digit TOTP code, got {code!r}"
        assert len(code) == 6

    def test_code_validates_against_secret(self):
        """The returned code must be cryptographically valid for the test TOTP secret."""
        with patch("app.services.filetrac_auth.get_settings",
                   return_value=_make_mock_settings(totp_secret=_TEST_TOTP_SECRET)):
            from app.services.filetrac_auth import get_totp_code
            code = get_totp_code()
        totp = pyotp.TOTP(_TEST_TOTP_SECRET)
        assert totp.verify(code, valid_window=1), f"TOTP code {code!r} did not verify"

    def test_works_without_filetrac_env_vars(self):
        """Must not raise KeyError when FILETRAC_TOTP_SECRET is absent from os.environ.

        Before the fix: os.environ["FILETRAC_TOTP_SECRET"] → KeyError.
        After the fix: get_settings().filetrac_totp_secret → reads from .env via pydantic.
        """
        with _EnvCleaned(), \
             patch("app.services.filetrac_auth.get_settings", return_value=_make_mock_settings()):
            from app.services.filetrac_auth import get_totp_code
            code = get_totp_code()  # must not raise
        assert len(code) == 6


# ── cognito_login_with_mfa ─────────────────────────────────────────────────────

class TestCognitoLoginWithMfa:
    """cognito_login_with_mfa() must pass credentials from get_settings() to Cognito."""

    def _run(self, mock_cognito_cls, settings=None):
        if settings is None:
            settings = _make_mock_settings()
        with patch("app.services.filetrac_auth.get_settings", return_value=settings), \
             patch("app.services.filetrac_auth.Cognito", mock_cognito_cls):
            from app.services.filetrac_auth import cognito_login_with_mfa
            return cognito_login_with_mfa()

    def _make_mock_cognito(self, access_token="access_tok", id_token="id_tok"):
        instance = MagicMock()
        instance.access_token = access_token
        instance.id_token = id_token
        return MagicMock(return_value=instance), instance

    def test_cognito_initialised_with_email_from_settings(self):
        """Cognito must be initialised with the email from settings, not os.environ."""
        mock_cls, _ = self._make_mock_cognito()
        self._run(mock_cls, _make_mock_settings(email="from_settings@catpro.com"))
        _, kwargs = mock_cls.call_args
        assert kwargs.get("username") == "from_settings@catpro.com"

    def test_authenticate_called_with_password_from_settings(self):
        """authenticate() must receive the password from settings, not os.environ."""
        mock_cls, instance = self._make_mock_cognito()
        self._run(mock_cls, _make_mock_settings(password="settings-pass"))
        instance.authenticate.assert_called_once_with(password="settings-pass")

    def test_works_without_filetrac_env_vars(self):
        """Must not raise KeyError when FILETRAC_EMAIL / FILETRAC_PASSWORD are absent
        from os.environ — the fix ensures credentials come from get_settings()."""
        mock_cls, _ = self._make_mock_cognito()
        with _EnvCleaned():
            access_token, id_token = self._run(mock_cls)
        assert access_token == "access_tok"
        assert id_token == "id_tok"

    def test_responds_to_mfa_challenge(self):
        """When authenticate() raises SoftwareTokenMFAChallengeException, the function
        must call respond_to_software_token_mfa_challenge() with a valid TOTP code."""
        from pycognito.exceptions import SoftwareTokenMFAChallengeException

        instance = MagicMock()
        instance.authenticate.side_effect = SoftwareTokenMFAChallengeException(
            "MFA required", {"Session": "fake-session"}
        )
        instance.access_token = "tok"
        instance.id_token = "id"
        mock_cls = MagicMock(return_value=instance)

        settings = _make_mock_settings(totp_secret=_TEST_TOTP_SECRET)
        with patch("app.services.filetrac_auth.get_settings", return_value=settings), \
             patch("app.services.filetrac_auth.Cognito", mock_cls):
            from app.services.filetrac_auth import cognito_login_with_mfa
            cognito_login_with_mfa()

        instance.respond_to_software_token_mfa_challenge.assert_called_once()
        code = instance.respond_to_software_token_mfa_challenge.call_args[0][0]
        assert code.isdigit() and len(code) == 6, f"Expected 6-digit TOTP, got {code!r}"

    def test_returns_access_and_id_tokens(self):
        """Return value must be (access_token, id_token) from the Cognito instance."""
        mock_cls, _ = self._make_mock_cognito(access_token="my_access", id_token="my_id")
        access, id_tok = self._run(mock_cls)
        assert access == "my_access"
        assert id_tok == "my_id"


# ── login ──────────────────────────────────────────────────────────────────────

class TestLogin:
    """login() must POST to evolveLogin with the right payload and verify ASPSESSIONID."""

    def _run_login(self, session, *, sub="test-sub-uuid"):
        """Run login() with mocked cognito_login_with_mfa and a real session with mocked post."""
        id_token = _make_id_token(sub=sub)

        fake_resp = MagicMock()
        fake_resp.url = "https://cms14.filetrac.net/system/claimList.asp"
        fake_resp.raise_for_status = MagicMock()

        def _post_side_effect(url, **kwargs):
            # Simulate the ASP server setting the session cookie
            session.cookies.set("ASPSESSIONIDAABBCC", "DDEEFFGG", domain="cms14.filetrac.net")
            return fake_resp

        session.post = MagicMock(side_effect=_post_side_effect)

        with patch("app.services.filetrac_auth.cognito_login_with_mfa",
                   return_value=("fake_access_token", id_token)):
            from app.services.filetrac_auth import login
            login(session)

    def _make_session(self):
        import requests
        return requests.Session()

    def test_session_has_aspsessionid_cookie_after_login(self):
        session = self._make_session()
        self._run_login(session)
        names = [c.name for c in session.cookies]
        assert any(n.startswith("ASPSESSIONID") for n in names), (
            f"No ASPSESSIONID cookie found after login; cookies: {names}"
        )

    def test_posts_to_evolve_login_url(self):
        from app.services.filetrac_auth import EVOLVE_LOGIN_URL
        session = self._make_session()
        self._run_login(session)
        posted_url = session.post.call_args[0][0]
        assert posted_url == EVOLVE_LOGIN_URL

    def test_payload_contains_sub_as_evolve_user_id(self):
        """The evolveUserId in the POST body must be the 'sub' claim from the id_token."""
        session = self._make_session()
        self._run_login(session, sub="my-cognito-sub-uuid")
        data = session.post.call_args[1]["data"]
        assert data["evolveUserId"] == "my-cognito-sub-uuid"

    def test_payload_contains_legacy_user_id(self):
        from app.services.filetrac_auth import FILETRAC_LEGACY_USER_ID
        session = self._make_session()
        self._run_login(session)
        data = session.post.call_args[1]["data"]
        assert data["userId"] == FILETRAC_LEGACY_USER_ID

    def test_raises_if_no_session_cookie_set(self):
        """login() must raise RuntimeError if evolveLogin response sets no ASPSESSIONID."""
        from app.services.filetrac_auth import login
        session = self._make_session()
        id_token = _make_id_token()

        fake_resp = MagicMock()
        fake_resp.url = "https://cms14.filetrac.net/system/claimList.asp"
        fake_resp.raise_for_status = MagicMock()
        session.post = MagicMock(return_value=fake_resp)  # no cookie set

        with patch("app.services.filetrac_auth.cognito_login_with_mfa",
                   return_value=("tok", id_token)):
            with pytest.raises(RuntimeError, match="evolveLogin did not set ASPSESSIONID"):
                login(session)
