# CatPro Claims Automation — Deployment Summary

**Date:** April 2, 2026
**Prepared by:** CatPro Engineering

---

## What We're Deploying

An automated claims processing system that reads incoming claim emails, extracts data from PDF attachments (starting with Acuity Insurance), and creates claims in FileTrac — eliminating manual data entry. A web dashboard provides real-time visibility into claim processing status, volume trends, and errors.

## Current State

The core pipeline is **built and working**:
- Email polling via Microsoft 365 Graph API
- PDF parsing and data extraction (Acuity format)
- Automated FileTrac authentication (Cognito + MFA + SSO)
- Claim creation with full field mapping
- Dry-run mode for safe testing (no billable claims created)
- SQLite database tracking all processed claims

## What We're Adding

| Component | Purpose |
|-----------|---------|
| **FastAPI Backend** | REST API serving claim data to the dashboard |
| **React Dashboard** | Real-time view of claim status, trends, and errors |
| **Docker Container** | Single deployable image for the full application |
| **Azure AI Foundry** | AI gateway for future multi-insurer PDF parsing |

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  Azure Container Apps                               │
│                                                     │
│  ┌─────────────┐    ┌──────────────────────────┐   │
│  │  Email       │    │  FastAPI + React          │   │
│  │  Poller      │───>│  (Dashboard + API)        │   │
│  │  (background)│    │                            │   │
│  └──────┬───────┘    └──────────┬────────────────┘   │
│         │                       │                    │
│         v                       v                    │
│  ┌──────────────────────────────────────────┐       │
│  │  SQLite (Azure Files volume)              │       │
│  │  + Scheduled backups                      │       │
│  └──────────────────────────────────────────┘       │
│                                                     │
└─────────────────────────────────────────────────────┘
         │                              │
         v                              v
   Microsoft 365                   FileTrac CMS
   (claim emails)              (claim submission)
```

## Monthly Cost Estimate

| Resource | Description | Est. Cost |
|----------|-------------|-----------|
| Azure Container Apps | App + poller (0.25 vCPU, 0.5 GB RAM) | $14 |
| Azure Container Registry | Docker image storage (Basic tier) | $5 |
| Azure Files | SQLite database + backups | < $1 |
| Azure AI Foundry | LLM calls for multi-insurer parsing (future) | $1–3 |
| **Total (current)** | | **~$19–20/mo** |
| **Total (with AI later)** | | **~$20–23/mo** |

### Cost Notes

- Based on East US region pricing, pay-as-you-go rates
- Container Apps includes a monthly free grant (180K vCPU-seconds) — actual compute cost may be lower
- AI Foundry is pay-per-token; estimate assumes 100–200 claims/month with LLM extraction
- No database server cost — SQLite on a file share is sufficient for 2–3 concurrent users at our volume
- If we later need PostgreSQL (for higher concurrency), add ~$17/mo

## Database & Backup Strategy

**SQLite with WAL mode** is the starting database. For our workload (single writer, 2–3 dashboard users, <200 claims/month), this is reliable and cost-effective.

**Backups** run on a 6-hour schedule using SQLite's built-in online backup API, which produces consistent snapshots even during active reads/writes. Backups are stored on Azure Files alongside the database.

**Migration path to PostgreSQL** is pre-built via SQLAlchemy ORM + Alembic migrations. If concurrent write volume or user count grows, switching to Azure Database for PostgreSQL is a configuration change, not a rewrite.

## Scaling Path

| Milestone | Action | Cost Impact |
|-----------|--------|-------------|
| Current (2–3 users, <200 claims/mo) | SQLite + single container | ~$20/mo |
| More insurers (AI parsing needed) | Add AI Foundry model access | +$1–3/mo |
| Higher concurrency (5+ users) | Swap SQLite for PostgreSQL | +$17/mo |
| High volume (background job queues) | Add Redis + Celery worker | +$30/mo |
| **Fully scaled** | | **~$70/mo** |

## Timeline

| Phase | Scope | Status |
|-------|-------|--------|
| Core pipeline (email → FileTrac) | Polling, parsing, auth, submission | Done |
| FastAPI backend + API | REST endpoints, service layer | Planned |
| React dashboard | Stats, trends, claims table, detail view | Planned |
| Docker + Azure deployment | Container build, Azure provisioning | Planned |
| AI Foundry integration | Multi-insurer PDF parsing | Future |

## Key Decisions

- **Start simple**: SQLite + single container. No premature infrastructure.
- **No authentication for v1**: internal tool, network-level access only (localhost / VPN).
- **Dry-run mode**: full pipeline testing without creating billable claims in FileTrac.
- **All infrastructure via Azure CLI**: reproducible, scriptable provisioning.

## Prerequisites

- Azure subscription under Catcrew Adjusting LLC (in progress)
- Existing Azure AD app registration for M365 email access (done)
- FileTrac credentials and TOTP secret (configured)
