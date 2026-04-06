"""Pydantic response schemas for the claims API."""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, computed_field, field_validator


class ClaimStats(BaseModel):
    total: int
    success: int
    error: int
    pending: int
    dry_run: int
    success_rate: float | None = None  # None when success + error == 0


class ClaimSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subject: str | None = None
    sender: str | None = None
    received_at: str | None = None
    processed_at: str
    claim_id: str | None = None
    status: str
    dry_run: bool = False
    error_message: str | None = None
    insured_first_name: str | None = None
    insured_last_name: str | None = None

    @computed_field
    @property
    def insured_name(self) -> str | None:
        if self.insured_last_name and self.insured_first_name:
            return f"{self.insured_last_name}, {self.insured_first_name}"
        return self.insured_last_name or self.insured_first_name


class ClaimListResponse(BaseModel):
    items: list[ClaimSummary]
    total: int
    page: int
    page_size: int
    stats: ClaimStats
    last_processed_at: str | None = None


class ClaimDataSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    insured_first_name: str | None = None
    insured_last_name: str | None = None
    insured_email: str | None = None
    insured_phone: str | None = None
    insured_cell: str | None = None
    insured_address1: str | None = None
    insured_city: str | None = None
    insured_state: str | None = None
    insured_zip: str | None = None
    secondary_insured_first: str | None = None
    secondary_insured_last: str | None = None
    policy_number: str | None = None
    policy_effective: str | None = None
    policy_expiration: str | None = None
    loss_date: str | None = None
    loss_type: str | None = None
    loss_description: str | None = None
    loss_address1: str | None = None
    loss_city: str | None = None
    loss_state: str | None = None
    loss_zip: str | None = None
    client_company_name: str | None = None
    client_claim_number: str | None = None
    agent_company: str | None = None
    agent_phone: str | None = None
    agent_email: str | None = None
    agent_address1: str | None = None
    agent_city: str | None = None
    agent_state: str | None = None
    agent_zip: str | None = None
    assigned_adjuster_name: str | None = None


# Keys to strip from resolved_ids and submission_payload
_REDACTED_RESOLVED_KEYS = {"csrf_token"}
_REDACTED_PAYLOAD_KEYS = {
    "pageLayout_CSRtoken",
    "insuredSSN",
    "insuredDriversLicense",
    "insuredDOB",
}


class ClaimDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subject: str | None = None
    sender: str | None = None
    received_at: str | None = None
    processed_at: str
    claim_id: str | None = None
    status: str
    dry_run: bool = False
    error_message: str | None = None
    claim_data: ClaimDataSchema | None = None
    resolved_ids: dict[str, str | None] | None = None
    submission_payload: dict | None = None

    @field_validator("resolved_ids", mode="before")
    @classmethod
    def redact_resolved_ids(cls, v):
        if isinstance(v, str):
            v = json.loads(v)
        if not isinstance(v, dict):
            return v
        return {k: val for k, val in v.items() if k not in _REDACTED_RESOLVED_KEYS}

    @field_validator("submission_payload", mode="before")
    @classmethod
    def redact_submission_payload(cls, v):
        if isinstance(v, str):
            v = json.loads(v)
        if not isinstance(v, dict):
            return v
        return {
            k: "[REDACTED]" if k in _REDACTED_PAYLOAD_KEYS else val
            for k, val in v.items()
        }


class TrendPoint(BaseModel):
    date: str
    total: int
    success: int
    error: int


class ClaimTrends(BaseModel):
    data: list[TrendPoint]


class HealthResponse(BaseModel):
    status: str  # "ok" | "degraded" | "unknown"
    last_processed_at: str | None = None
    recent_error_rate: float | None = None
    poll_interval: int


class ErrorResponse(BaseModel):
    detail: str


class AppConfigSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dry_run: bool
    test_mode: bool
    test_adjuster_id: str
    test_branch_id: str
    updated_at: str | None = None
    poller_enabled: bool = True
    poll_interval_seconds: int = 60
    poller_status: str | None = None
    last_heartbeat: str | None = None
    last_run_at: str | None = None
    last_error: str | None = None


class AppConfigUpdate(BaseModel):
    dry_run: bool | None = None
    test_mode: bool | None = None
    test_adjuster_id: str | None = None
    test_branch_id: str | None = None
    poller_enabled: bool | None = None
    poll_interval_seconds: int | None = None


class PollerProcessStatus(BaseModel):
    running: bool
    pid: int | None = None


class PollerLogsResponse(BaseModel):
    lines: list[str]


class TestEmailRequest(BaseModel):
    ref: str = "9999"
    adjuster: str = "Alan"
    subject: str | None = None


# ── Triage / Email log schemas ───────────────────────────────────────────────

class EmailActionEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    action_type: str
    actor: str
    details: dict | None = None
    created_at: str

    @field_validator("details", mode="before")
    @classmethod
    def parse_details(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, ValueError):
                return None
        return v


class InboxEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subject: str | None = None
    sender: str | None = None
    received_at: str | None = None
    processed_at: str
    status: str
    triage_status: str
    dry_run: bool = False
    error_message: str | None = None
    error_traceback: str | None = None
    error_phase: str | None = None
    insured_name: str | None = None


class InboxCountResponse(BaseModel):
    count: int


class InboxResponse(BaseModel):
    items: list[InboxEntry]
    total: int
    page: int
    page_size: int


class EmailLogStats(BaseModel):
    total: int
    success: int   # real FileTrac claims (not dry_run)
    dry_run: int   # dry-run completions
    skipped: int
    error: int
    # NOTE: needs_review intentionally omitted — /inbox/count is the source of truth


class EmailLogEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subject: str | None = None
    sender: str | None = None
    received_at: str | None = None
    processed_at: str
    status: str
    triage_status: str
    dry_run: bool = False
    claim_id: str | None = None
    error_message: str | None = None
    error_traceback: str | None = None
    error_phase: str | None = None
    insured_name: str | None = None
    body_text: str | None = None


class EmailLogDetail(EmailLogEntry):
    """Extends EmailLogEntry with the full action timeline."""

    actions: list[EmailActionEntry] = []


class EmailLogResponse(BaseModel):
    items: list[EmailLogEntry]
    total: int
    page: int
    page_size: int
    stats: EmailLogStats


class TriageActionRequest(BaseModel):
    # Pydantic Literal provides automatic 422 — no manual dict lookup needed
    action: Literal["flag_review", "dismiss", "approve"]
    # actor intentionally omitted — hardcoded to "admin" in route until auth exists
