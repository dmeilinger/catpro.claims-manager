"""Centralized configuration loaded from .env."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env relative to the repo root (one level up from backend/)
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # FileTrac credentials
    filetrac_email: str = ""
    filetrac_password: SecretStr = SecretStr("")
    filetrac_totp_secret: SecretStr = SecretStr("")

    # Azure AD app registration (CatPro tenant)
    azure_tenant_id: str = ""
    azure_client_id: str = ""
    azure_client_secret: SecretStr = SecretStr("")

    # Shared mailbox to poll
    m365_mailbox: str = ""

    # Polling
    poll_interval_seconds: int = 60
    db_path: str = "data/claims.db"

    # Claim submission behaviour
    dry_run: bool = True   # skip final POST to FileTrac (safe default)
    test_mode: bool = True  # override adjuster/branch with test account values
    test_adjuster_id: str = "342436"   # Bob TEST
    test_branch_id: str = "2529"       # TEST branch
    test_company_id: str = "143898"    # Test Company — used instead of real insurer in test mode
    # Numeric FileTrac claim ID to UPDATE instead of creating a new claim.
    # Set this to a permanent "sandbox" claim so tests never incur charges.
    # Leave empty to create a new claim (only use in production).
    filetrac_test_claim_id: str = ""

    # API server
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
