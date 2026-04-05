"""Centralized configuration loaded from .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # FileTrac credentials (existing)
    filetrac_email: str = ""
    filetrac_password: str = ""
    filetrac_totp_secret: str = ""

    # Azure AD app registration (CatPro tenant)
    azure_tenant_id: str = ""
    azure_client_id: str = ""
    azure_client_secret: str = ""

    # Shared mailbox to poll
    m365_mailbox: str = ""  # e.g. "claims@catpro.us.com"

    # Polling
    poll_interval_seconds: int = 60
    db_path: str = "data/claims.db"

    # Dry run — full pipeline except the final claim submission POST (legacy fallback only)
    dry_run: bool = False


def get_settings() -> Settings:
    return Settings()
