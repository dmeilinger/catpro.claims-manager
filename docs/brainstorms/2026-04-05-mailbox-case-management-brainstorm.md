---
date: 2026-04-05
topic: mailbox-case-management
---

# Mailbox Case Management

## What We're Building

A case management system layered on top of the existing M365 mailbox poller. Every email the
poller sees becomes a **case** with a triage lifecycle. Today, humans are the actors — they can
classify, dismiss, or action cases manually via an admin UI. When an AI agent is attached, it
becomes another actor in the same workflow, doing what humans do today, automatically. Humans
shift to handling only escalations.

The system has two UI surfaces:
1. **Admin > Inbox** — active queue of cases needing attention, with action buttons
2. **Admin > Email History** — full paginated audit trail and agent monitoring surface

## Why This Approach

Three approaches were considered:

- **A (Audit log, retrofit later):** Read-only log now, redesign when agent arrives. Rejected
  because the UI redesign cost and data model migration are higher later than now.
- **B (Case model now, agent slots in later):** Full workflow data model today with humans as
  actors. Agent arrives and slots into the same workflow without re-architecture. **Chosen.**
- **C (Agent-first):** Design agent tools first, build UI as oversight console. Rejected because
  it requires a clear agent spec before any UI work can happen, and delivers nothing useful to
  humans in the meantime.

## Key Decisions

- **Email = Case:** Each row in `processed_emails` is a case with a triage lifecycle, not just
  a log entry. Status reflects workflow state, not just technical outcome.

- **`triage_status` field:** `unreviewed | needs_review | actioned | archived` — separate from
  the existing `status` field (`success | error | skipped | pending`). The existing `status`
  records what the *poller* did; `triage_status` records where the *case* is in the human/agent
  workflow.

- **`email_actions` table:** Records every action taken on a case — who did it (poller, agent,
  or a named human), what they did (created_claim, sent_reply, routed_adjuster, flagged_review,
  dismissed), and when. This is the audit trail of agent behavior from day one.

- **Agent fields on `processed_emails` (nullable now):**
  - `agent_classification`: `new_claim | follow_up | non_claim | unknown`
  - `agent_confidence`: float 0–1
  - `agent_reasoning`: text — why the agent made its decision
  These are null until the agent is wired up. The UI shows them when present.

- **Inbox = human-actionable queue today:** The Inbox view shows cases with
  `triage_status = needs_review`. Today humans populate this by manually flagging cases. When
  the agent arrives, it populates it automatically and humans only see escalations.

- **Dedicated claims inbox:** This mailbox is claims-only. Other email types (follow-ups,
  non-PDF claims, junk) are valid cases that need triage, not noise to be filtered silently.

- **Don't mark emails read in the mailbox:** Humans actively work in this shared mailbox. The
  poller observes without interfering with human workflows. Marking as read is reserved for
  emails the poller has fully resolved.

## Data Model Changes

### `processed_emails` — new columns
```
triage_status        TEXT DEFAULT 'unreviewed'   -- unreviewed | needs_review | actioned | archived
agent_classification TEXT                        -- new_claim | follow_up | non_claim | unknown
agent_confidence     REAL                        -- 0.0–1.0, null until agent present
agent_reasoning      TEXT                        -- agent's explanation, null until agent present
```

### New table: `email_actions`
```sql
CREATE TABLE email_actions (
    id          INTEGER PRIMARY KEY,
    email_id    INTEGER NOT NULL REFERENCES processed_emails(id),
    action_type TEXT NOT NULL,  -- created_claim | sent_reply | routed_adjuster |
                                --   flagged_review | dismissed | classified | approved
    actor       TEXT NOT NULL,  -- 'poller' | 'agent' | username
    details     TEXT,           -- JSON: claim_id, reply_body, adjuster_id, reason, etc.
    created_at  TEXT NOT NULL
);
```

## UI Structure

### Admin > Inbox (`/admin/inbox`)
- Default view: cases with `triage_status = needs_review`
- Each row: received time, sender, subject, classification (if agent present), confidence badge
- Action buttons per row: **Approve** / **Dismiss** / **Override** (opens detail)
- Agent reasoning shown inline when present
- Empty state: "No cases need review" (healthy signal)

### Admin > Email History (`/admin/email-history`)
- Full paginated table: all emails, all statuses
- Filters: triage_status, poller status, date range, sender/subject search
- Stats bar: Total | Processed | Skipped | Needs Review | Errors
- Row expand: full timeline of `email_actions` for that case
- Read-only; actions surface is the Inbox

### Email case detail (expandable row or side panel)
- Email metadata: subject, sender, received/processed timestamps
- Poller outcome: status + error/skip reason
- Agent block (shown when populated): classification, confidence, reasoning
- Action timeline: chronological list from `email_actions`
- Action buttons (if `triage_status = needs_review`)

## Resolved Decisions

- **Sidebar placement:** Inbox is a **top-level nav item** alongside Dashboard and Claims — not
  under Admin. It's a primary action surface, not a settings page.
- **Unread badge:** The Inbox nav item shows a live count of cases with `triage_status =
  needs_review`. Treat it like an unread indicator — clears as cases are actioned.
- **Reply drafting:** Deferred to agent phase. The UI will not have a compose surface now.
  When the agent arrives it drafts replies; humans approve via the Inbox action buttons.
- **Graph pagination:** Fix `$top=10` blind spot in this pass. Implement `@odata.nextLink`
  pagination in `GraphMailSource.fetch_unread()` so all unread emails are visible to the
  poller regardless of inbox volume.

## Next Steps

→ `/ce:plan` for implementation details — migrations, backend endpoints, frontend pages
