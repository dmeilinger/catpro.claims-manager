"""API route handlers for /api/v1/claims and /api/v1/health."""

import json
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, contains_eager, joinedload

from app.config import Settings, get_settings
from app.database import get_db
from app.models import AppConfig, ClaimData, ProcessedEmail
from app import poller_manager
from app.schemas import (
    AppConfigSchema,
    AppConfigUpdate,
    ClaimDetail,
    ClaimDataSchema,
    ClaimListResponse,
    ClaimStats,
    ClaimSummary,
    ClaimTrends,
    HealthResponse,
    PollerLogsResponse,
    PollerProcessStatus,
    TrendPoint,
)

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def _escape_like(search: str) -> str:
    """Escape LIKE wildcards in search term."""
    return search.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


def _compute_stats(session: Session, base_query) -> ClaimStats:
    """Compute aggregate stats from a base query."""
    subq = base_query.subquery()
    total = session.scalar(select(func.count()).select_from(subq)) or 0

    success = session.scalar(
        select(func.count()).select_from(subq).where(
            subq.c.status == "success", subq.c.dry_run == False  # noqa: E712
        )
    ) or 0
    error = session.scalar(
        select(func.count()).select_from(subq).where(subq.c.status == "error")
    ) or 0
    pending = session.scalar(
        select(func.count()).select_from(subq).where(subq.c.status == "pending")
    ) or 0
    dry_run = session.scalar(
        select(func.count()).select_from(subq).where(subq.c.dry_run == True)  # noqa: E712
    ) or 0

    denominator = success + error
    success_rate = round(success / denominator, 4) if denominator > 0 else None

    return ClaimStats(
        total=total,
        success=success,
        error=error,
        pending=pending,
        dry_run=dry_run,
        success_rate=success_rate,
    )


@router.get("/claims", response_model=ClaimListResponse)
def list_claims(
    session: SessionDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    status: str | None = None,
    search: str | None = None,
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    sort_by: str = "processed_at",
    sort_order: str = "desc",
):
    """Paginated claims list with inline stats."""
    # Base query for filtering
    base = select(ProcessedEmail)

    if status:
        base = base.where(ProcessedEmail.status == status)
    if from_date:
        base = base.where(ProcessedEmail.processed_at >= from_date)
    if to_date:
        base = base.where(ProcessedEmail.processed_at <= to_date + "T23:59:59")

    # Search requires explicit JOIN to filter on ClaimData columns
    if search and len(search) >= 2:
        escaped = _escape_like(search)
        pattern = f"%{escaped}%"
        base = base.outerjoin(ClaimData).where(
            or_(
                ProcessedEmail.subject.ilike(pattern, escape="\\"),
                ClaimData.insured_first_name.ilike(pattern, escape="\\"),
                ClaimData.insured_last_name.ilike(pattern, escape="\\"),
                ClaimData.policy_number.ilike(pattern, escape="\\"),
                ClaimData.client_claim_number.ilike(pattern, escape="\\"),
            )
        )

    # Stats from same base query (same transaction = consistent)
    stats = _compute_stats(session, base)

    # Last processed timestamp
    last_processed = session.scalar(
        select(func.max(ProcessedEmail.processed_at))
    )

    # Total count
    total = session.scalar(select(func.count()).select_from(base.subquery()))

    # Sorting
    sort_col = getattr(ProcessedEmail, sort_by, ProcessedEmail.processed_at)
    order = sort_col.desc() if sort_order == "desc" else sort_col.asc()

    # Data query with eager loading
    data_query = base.options(joinedload(ProcessedEmail.claim_data))
    if search and len(search) >= 2:
        # Already joined above — use contains_eager instead
        data_query = base.options(contains_eager(ProcessedEmail.claim_data))

    rows = (
        session.scalars(
            data_query.order_by(order)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .unique()
        .all()
    )

    # Build response items with insured name from joined claim_data
    items = []
    for row in rows:
        cd = row.claim_data
        items.append(
            ClaimSummary(
                id=row.id,
                subject=row.subject,
                sender=row.sender,
                received_at=row.received_at,
                processed_at=row.processed_at,
                claim_id=row.claim_id,
                status=row.status,
                dry_run=row.dry_run,
                error_message=row.error_message,
                insured_first_name=cd.insured_first_name if cd else None,
                insured_last_name=cd.insured_last_name if cd else None,
            )
        )

    return ClaimListResponse(
        items=items,
        total=total or 0,
        page=page,
        page_size=page_size,
        stats=stats,
        last_processed_at=last_processed,
    )


@router.get("/claims/{claim_id:int}", response_model=ClaimDetail)
def get_claim(claim_id: int, session: SessionDep):
    """Full claim detail with joined data and redacted sensitive fields."""
    row = session.scalar(
        select(ProcessedEmail)
        .options(joinedload(ProcessedEmail.claim_data))
        .where(ProcessedEmail.id == claim_id)
    )
    if not row:
        raise HTTPException(status_code=404, detail="Claim not found")

    cd = row.claim_data

    # Build resolved_ids dict from claim_data columns
    resolved_ids = None
    if cd:
        resolved_ids = {
            "company_id": cd.filetrac_company_id,
            "contact_id": cd.filetrac_contact_id,
            "branch_id": cd.filetrac_branch_id,
            "adjuster_id": cd.filetrac_adjuster_id,
            "manager_id": cd.filetrac_manager_id,
            # csrf_token is redacted by the schema validator
            "csrf_token": cd.filetrac_csrf_token,
        }

    # Parse submission_payload from JSON string
    payload = None
    if cd and cd.submission_payload:
        try:
            payload = json.loads(cd.submission_payload)
        except (json.JSONDecodeError, TypeError):
            payload = None

    return ClaimDetail(
        id=row.id,
        subject=row.subject,
        sender=row.sender,
        received_at=row.received_at,
        processed_at=row.processed_at,
        claim_id=row.claim_id,
        status=row.status,
        dry_run=row.dry_run,
        error_message=row.error_message,
        claim_data=ClaimDataSchema.model_validate(cd) if cd else None,
        resolved_ids=resolved_ids,
        submission_payload=payload,
    )


@router.get("/claims/trends", response_model=ClaimTrends)
def get_trends(
    session: SessionDep,
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
):
    """Daily claim volume for chart. Defaults to last 30 days, zero-filled."""
    if not to_date:
        to_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if not from_date:
        from_dt = datetime.now(timezone.utc) - timedelta(days=30)
        from_date = from_dt.strftime("%Y-%m-%d")

    # Query daily counts grouped by date
    rows = session.execute(
        select(
            func.substr(ProcessedEmail.processed_at, 1, 10).label("day"),
            ProcessedEmail.status,
            func.count().label("cnt"),
        )
        .where(ProcessedEmail.processed_at >= from_date)
        .where(ProcessedEmail.processed_at <= to_date + "T23:59:59")
        .group_by("day", ProcessedEmail.status)
    ).all()

    # Aggregate into a dict
    day_data: dict[str, dict[str, int]] = {}
    for day, status, cnt in rows:
        if day not in day_data:
            day_data[day] = {"total": 0, "success": 0, "error": 0}
        day_data[day]["total"] += cnt
        if status in ("success", "error"):
            day_data[day][status] += cnt

    # Zero-fill missing days
    from_dt = datetime.strptime(from_date, "%Y-%m-%d")
    to_dt = datetime.strptime(to_date, "%Y-%m-%d")
    data = []
    current = from_dt
    while current <= to_dt:
        day_str = current.strftime("%Y-%m-%d")
        entry = day_data.get(day_str, {"total": 0, "success": 0, "error": 0})
        data.append(
            TrendPoint(
                date=day_str,
                total=entry["total"],
                success=entry["success"],
                error=entry["error"],
            )
        )
        current += timedelta(days=1)

    return ClaimTrends(data=data)


@router.get("/health", response_model=HealthResponse)
def health_check(session: SessionDep, settings: SettingsDep):
    """System health check — poller heartbeat recency + recent error rate."""
    last_processed = session.scalar(
        select(func.max(ProcessedEmail.processed_at))
    )

    # Use poller heartbeat to determine if the poller is alive
    cfg = _get_or_create_config(session)
    last_heartbeat = cfg.last_heartbeat

    # Recent error rate (last hour)
    hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    recent_total = session.scalar(
        select(func.count()).where(ProcessedEmail.processed_at >= hour_ago)
    ) or 0
    recent_errors = session.scalar(
        select(func.count()).where(
            ProcessedEmail.processed_at >= hour_ago,
            ProcessedEmail.status == "error",
        )
    ) or 0
    error_rate = round(recent_errors / recent_total, 4) if recent_total > 0 else None

    # Health is based on heartbeat recency, not last processed claim
    health_status = "unknown"
    if last_heartbeat:
        try:
            hb_dt = datetime.fromisoformat(last_heartbeat)
            age = datetime.now(timezone.utc) - hb_dt
            if age <= timedelta(seconds=settings.poll_interval_seconds * 2):
                health_status = "ok"
            else:
                health_status = "degraded"
        except ValueError:
            health_status = "unknown"

    if error_rate is not None and error_rate > 0.5:
        health_status = "degraded"

    return HealthResponse(
        status=health_status,
        last_processed_at=last_processed,
        recent_error_rate=error_rate,
        poll_interval=settings.poll_interval_seconds,
    )


def _get_or_create_config(session: Session) -> AppConfig:
    """Return the singleton AppConfig row, creating it with defaults if absent."""
    cfg = session.get(AppConfig, 1)
    if cfg is None:
        cfg = AppConfig(
            id=1, dry_run=False, test_mode=False,
            test_adjuster_id="342436", test_branch_id="2529",
            poller_enabled=True,
        )
        session.add(cfg)
        session.commit()
        session.refresh(cfg)
    return cfg


@router.get("/config", response_model=AppConfigSchema)
def get_config(session: SessionDep):
    """Return the singleton application configuration."""
    return _get_or_create_config(session)


@router.put("/config", response_model=AppConfigSchema)
def update_config(body: AppConfigUpdate, session: SessionDep):
    """Partially update the application configuration."""
    from datetime import datetime, timezone

    cfg = _get_or_create_config(session)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(cfg, field, value)
    cfg.updated_at = datetime.now(timezone.utc).isoformat()
    session.commit()
    session.refresh(cfg)
    return cfg


@router.get("/poller/status", response_model=PollerProcessStatus)
def get_poller_status():
    """Return whether the poller subprocess is currently running."""
    return PollerProcessStatus(running=poller_manager.is_running(), pid=poller_manager.get_pid())


@router.post("/poller/start", response_model=PollerProcessStatus)
def start_poller():
    """Spawn the poller subprocess if not already running."""
    poller_manager.start()
    return PollerProcessStatus(running=poller_manager.is_running(), pid=poller_manager.get_pid())


@router.post("/poller/stop", response_model=PollerProcessStatus)
def stop_poller():
    """Terminate the poller subprocess."""
    poller_manager.stop()
    return PollerProcessStatus(running=poller_manager.is_running(), pid=poller_manager.get_pid())


@router.get("/poller/logs", response_model=PollerLogsResponse)
def get_poller_logs(lines: int = Query(200, ge=1, le=1000)):
    """Return the last N lines from the poller log file."""
    return PollerLogsResponse(lines=poller_manager.read_logs(lines))
