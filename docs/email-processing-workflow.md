# Email Processing Workflow

End-to-end flow for every email the poller touches — from M365 inbox to FileTrac claim and human triage.

```mermaid
flowchart TD
    %% ── INBOUND ───────────────────────────────────────────────────────────────
    MAILBOX[(M365 Shared Mailbox<br/>claims-test@catpro.us.com)]
    POLLER[Poller<br/>poll_once every N seconds]

    MAILBOX -->|Graph API — two-phase fetch<br/>metadata list + per-msg attachments| POLLER

    %% ── FILTER ───────────────────────────────────────────────────────────────
    POLLER -->|has PDF attachment?| FILTER{PDF<br/>attachment?}

    FILTER -->|No| SKIP[status=skipped<br/>triage_status=unreviewed<br/>body_text stored]
    FILTER -->|Duplicate internet_message_id?| DUP{Already in DB?}
    DUP -->|Yes| MARKREAD[mark_read only<br/>no DB insert]
    DUP -->|No — has PDF| PENDING[status=pending<br/>triage_status=unreviewed<br/>body_text stored]

    %% ── EXTRACTION ───────────────────────────────────────────────────────────
    PENDING --> EXTRACT[extract_claim_fields<br/>pdf_extractor — pdfplumber<br/>regex parse Acuity layout]

    EXTRACT -->|Exception| ERR1[status=error<br/>triage_status=needs_review<br/>leave unread in inbox]

    EXTRACT -->|ClaimData| SUBMIT

    %% ── SUBMISSION ───────────────────────────────────────────────────────────
    subgraph SUBMIT [FileTrac Submission — read-only steps always run]
        AUTH[Cognito SRP + TOTP<br/>evolveLogin SSO → ASPSESSIONID]
        CSRF[GET claimAdd.asp<br/>extract CSRF token]
        RESOLVE[Resolve dynamic IDs<br/>companyID · contactID<br/>branchID · adjusterID · managerID]
        TESTCHECK{TEST_MODE=true?}
        TESTIDS[Substitute test account IDs<br/>Bob TEST adjuster + TEST branch]
        DRYCHECK{DRY_RUN=true?}
        POST[POST claimSave.asp<br/>~80-field payload]
        AUTH --> CSRF --> RESOLVE --> TESTCHECK
        TESTCHECK -->|Yes| TESTIDS --> DRYCHECK
        TESTCHECK -->|No| DRYCHECK
        DRYCHECK -->|No| POST
    end

    DRYCHECK -->|Yes — payload built<br/>POST skipped| DRYRESULT[claim_id=DRY_RUN<br/>full payload saved to SQLite<br/>no claim created in FileTrac]

    POST -->|Exception → re-auth + retry once| RETRY{Retry<br/>succeeded?}
    RETRY -->|No| ERR2[status=error<br/>triage_status=needs_review<br/>partial claim_data saved<br/>leave unread in inbox]
    RETRY -->|Yes| SUCCESS

    POST --> SUCCESS[status=success<br/>triage_status=unreviewed<br/>EmailAction: created_claim / actor=poller<br/>claim_data saved · mark_read]

    %% ── TRIAGE ───────────────────────────────────────────────────────────────
    SUCCESS -->|visible in Email History<br/>no human action required| HISTORY_UI
    DRYRESULT --> HISTORY_UI
    SKIP --> HISTORY_UI
    HISTORY_UI[Email History UI<br/>full audit trail — all emails]

    ERR1 --> INBOX_UI[Inbox UI<br/>badge = count of needs_review]
    ERR2 --> INBOX_UI

    subgraph TRIAGE [Human Triage — PATCH /email-log/:id/triage]
        FLAG[flag_review<br/>triage_status=needs_review<br/>promotes to Inbox]
        DISMISS[dismiss<br/>triage_status=actioned]
        APPROVE[approve<br/>triage_status=actioned]
    end

    INBOX_UI --> TRIAGE
    HISTORY_UI -->|optional: flag for review| FLAG

    TRIAGE -->|EmailAction logged<br/>actor=admin| DONE[(DB: email_actions<br/>audit trail)]
```

## Key design decisions

**Triage states**

| `triage_status` | Set by | Meaning |
|---|---|---|
| `unreviewed` | Poller (all outcomes) | Default — not yet examined by a human |
| `needs_review` | Poller (errors) or human `flag_review` | In the Inbox action queue |
| `actioned` | Human `dismiss` or `approve` | Resolved; distinction captured in `email_actions` |

- **The happy path is fully automated** — if the PDF parses cleanly and the FileTrac submission succeeds, the claim is created with no human intervention. The email is marked read and the record sits in Email History at `unreviewed`. No action required.
- **Errors land in the Inbox automatically** (`needs_review`) — no human action needed to surface them. A human must resolve them.
- **Successes stay at `unreviewed`** — visible in Email History but not in the Inbox. A human can optionally `flag_review` → `approve`/`dismiss`, but it is not required for the claim to exist in FileTrac.
- **`approve` and `dismiss` both set `actioned`** — the difference is recorded in `email_actions.action_type`, not duplicated as a fourth triage state.

**Email paths**

- **Skipped** (no PDF): inserted once, never re-processed; visible in Email History only. `body_text` is stored so a future classification agent can act on it.
- **Duplicate**: `mark_read` and move on — no second DB row.
- **Extraction failure**: `status=error`, left unread in the shared mailbox for manual review.
- **Submission failure**: `status=error`, partial `claim_data` saved, left unread. Re-auth + single retry before giving up.

**Config modes** (combinable)

| | `DRY_RUN=false` | `DRY_RUN=true` |
|---|---|---|
| `TEST_MODE=false` | Production: real IDs, claim created | Preview: real IDs, payload saved, no POST |
| `TEST_MODE=true` | Test claim: Bob TEST adjuster + TEST branch | Dev: test IDs, payload saved, no POST |

`DRY_RUN` gates only the final `POST claimSave.asp`. All prior steps — auth, CSRF fetch, ID resolution — run in both modes. The fully-built payload is saved to SQLite so you can inspect exactly what would have been sent.

## Related files

- [`backend/app/services/poller.py`](../backend/app/services/poller.py) — `poll_once`, all DB helpers
- [`backend/app/services/email_source.py`](../backend/app/services/email_source.py) — `GraphMailSource`, two-phase fetch, `@odata.nextLink` pagination
- [`backend/app/services/pdf_extractor.py`](../backend/app/services/pdf_extractor.py) — `extract_claim_fields`, Acuity PDF parsing
- [`backend/app/services/filetrac_submit.py`](../backend/app/services/filetrac_submit.py) — `submit_claim`, FileTrac ID resolution, DRY_RUN gate
- [`backend/app/models.py`](../backend/app/models.py) — `ProcessedEmail`, `ClaimData`, `EmailAction` ORM models
- [`backend/app/routes.py`](../backend/app/routes.py) — triage endpoints (`/inbox`, `/email-log`, `/email-log/:id/triage`)
