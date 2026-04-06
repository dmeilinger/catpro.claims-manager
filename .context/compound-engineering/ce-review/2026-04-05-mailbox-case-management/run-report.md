# CE Review Run — feat/mailbox-case-management
Date: 2026-04-05
Base: 3d7ce646a6272159c96265b2780a609bd5874d5d
Branch: feat/mailbox-case-management
Plan: docs/plans/2026-04-05-feat-mailbox-case-management-plan.md

## Reviewers Run
- correctness-reviewer ✅
- security-reviewer ✅
- kieran-python-reviewer ✅
- kieran-typescript-reviewer ✅
- data-migrations-reviewer ✅
- testing-reviewer ✅
- performance-reviewer ✅

## Applied Fixes (safe_auto)

### P1
- **email_source.py: _ensure_folder and mark_read bypass self._request()** — Replaced all raw `http_requests.*` calls with `self._request()` so 401 token refresh applies to mark_read and folder operations, not just fetch_unread.

### P2
- **routes.py: triage_email missing joinedload(claim_data)** — Added re-query after commit using both `joinedload(claim_data)` and `selectinload(actions)` so the new EmailAction appears in the response and insured_name is populated.
- **routes.py: list_email_log redundant COUNT subquery** — Replaced second `base.subquery()` COUNT with `stats.total` (already computed by `_compute_email_log_stats`). Single shared `sq` variable.
- **routes.py: insured_name duplicated across 3 callsites** — Extracted `_insured_name(cd)` helper; three inline blocks replaced with one-liners.
- **TypeScript: action param untyped** — Added `TriageAction = "flag_review" | "dismiss" | "approve"` to schemas/email.ts; `useTriageAction` mutationFn now uses it.
- **TypeScript: optimistic update doesn't decrement total** — `setQueryData` updater now also decrements `total` (clamped to 0) so pagination math stays correct after dismiss.

### P3
- **test_email_source.py: page cap assertion too loose** — Changed `<= 20` to `== 20` to pin the MAX_PAGES boundary exactly.
- **conftest.py: unused `sessionmaker` import** — Removed.
- **models.py: duplicate ix_processed_emails_triage_status** — Removed from `__table_args__` (managed by migration only).

## Residual Findings (gated_auto / manual — not auto-applied)

### P0
- **All mutation endpoints unauthenticated** (security) — No auth middleware. Required before any shared/internet deployment. Affects PATCH /triage, PUT /config, POST /poller/start|stop, POST /send-test-email.

### P1
- **useTriageAction optimistic update targets bare ['inbox'] key** (TS) — `getQueryData/setQueryData` use exact matching; `['inbox', params]` cache entries are never updated optimistically. Use `setQueriesData({queryKey: ['inbox']}, updater)`.
- **_mark_error writes no EmailAction row** (testing) — Audit trail is silent on failures. Add `action_type='processing_error'` row in `_mark_error`.

### P2
- **conftest.py: Session(bind=connection) deprecated in SQLAlchemy 2.x** — Will break on SA 2.0 upgrade.
- **triage_status is bare str throughout** — No Zod enum or Pydantic Literal at schema boundaries.
- **Dry Run filter chip is a no-op** — `handleStatusFilter` converts 'dry_run' to null; backend needs separate `?dry_run=true` param.
- **list_email_log stats can diverge from data when outerjoin active** — No DISTINCT on count when search joins ClaimData.
- **FK without CASCADE makes processed_emails undeletable once actioned** — Intentional but needs documented escape hatch.
- **Unvalidated date string params** — No format validation on from/to; garbage values silently return empty results.

### P3 (advisory)
- Migration downgrade permanently destroys email_actions data (mark as irreversible or add export step).
- triage_status has no SQLite CHECK constraint — invalid values accepted silently.
- body_text unbounded size — truncate at ~50KB at extraction time.
- Missing composite index (triage_status, received_at) for /inbox query.

## Test Results
67/67 passing. TypeScript: clean.
