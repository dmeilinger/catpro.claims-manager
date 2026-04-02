---
date: 2026-04-01
topic: fastapi-react-dashboard
---

# FastAPI + React Claims Dashboard

## What We're Building

A monorepo FastAPI + React application for CatPro claim automation. The existing `catpro/` pipeline gets consolidated into the FastAPI backend as a service layer, importable by both API routes and standalone scripts (CLI, poller, test email). The React frontend provides a Cursor-styled dark dashboard with summary stats, daily trend charts, and a full claims table with detail view.

## Why This Approach

- **Consolidate catpro into backend services** (option A): avoids import gymnastics, single Docker image, one place to maintain. Preferred over keeping catpro as a separate package or wrapping it with a facade.
- **Monorepo**: backend/ + frontend/ at the top level. Simple, Docker-friendly, single repo for all deployment artifacts.
- **SQLAlchemy + Alembic**: abstracts the SQLite-to-Postgres migration path. ORM models replace raw SQL in catpro/db.py.
- **No auth for v1**: internal tool, add later when needed.
- **Poller as separate process**: simpler than in-process background tasks. Celery planned for eventual task management.

## Key Decisions

- **catpro/ moves into backend/app/services/**: claim_processor, email_source, poller, test_email, db become service modules
- **SQLAlchemy 2.0 ORM**: replaces raw SQLite queries, enables future Postgres swap via Alembic migrations
- **Frontend mirrors ai-reporting stack**: React 19 + TypeScript + Vite + Tailwind (HSL dark theme, #121212 bg, #22c55e green accent) + Zustand + React Query + Recharts + Lucide
- **Custom components**: DataTable, SummaryCards, FilterPanel, StatusBadge — no component library dependency
- **Poller**: separate process now, Celery eventually
- **Docker**: eventual deployment to PaaS as container image

## Tech Stack

### Backend
- FastAPI + Pydantic v2 (response/request schemas)
- SQLAlchemy 2.0 (ORM models for processed_emails + claim_data)
- Alembic (database migrations)
- Python 3.13

### Frontend
- React 19 + TypeScript + Vite
- Tailwind CSS 3.x with HSL dark theme tokens (Cursor aesthetic)
- Zustand (UI state) + TanStack React Query (server state)
- Recharts (charts), Lucide React (icons)
- Axios (HTTP client), date-fns (dates)

## API Surface (v1)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/claims` | GET | Paginated list with filters (status, date range, text search) |
| `/api/claims/{id}` | GET | Full detail: email metadata + claim_data + resolved IDs + payload |
| `/api/claims/stats` | GET | Summary counts: total, success, error, pending, success rate |
| `/api/claims/trends` | GET | Daily claim volume over time (for chart) |

## UI Views (v1)

### Dashboard Page
- **Summary cards**: total claims, success rate, errors, pending count
- **Daily trend chart**: line chart of claim volume over time (Recharts)
- **Claims table**: sortable columns (date, subject, insured, status, claim ID), status badges, click to expand
- **Detail drawer/sheet**: full claim data, resolved FileTrac IDs, submission payload JSON, error message if failed
- **Filters**: date range picker, status dropdown, text search (insured name, policy #, subject)

## Project Structure

```
backend/
├── app/
│   ├── main.py              — FastAPI app, CORS, lifespan
│   ├── core/
│   │   ├── config.py        — Pydantic Settings (evolved from catpro/config.py)
│   │   └── database.py      — SQLAlchemy engine + session factory
│   ├── models/
│   │   ├── email.py          — ProcessedEmail ORM model
│   │   └── claim.py          — ClaimData ORM model
│   ├── schemas/
│   │   ├── claim.py          — Pydantic response/request schemas
│   │   └── stats.py          — Stats response schema
│   ├── api/
│   │   └── claims.py         — /api/claims routes
│   └── services/
│       ├── claim_processor.py — from catpro/process_claim.py
│       ├── email_source.py    — from catpro/email_source.py
│       ├── db.py              — legacy compat or replaced by SQLAlchemy
│       ├── poller.py          — from catpro/poller.py
│       └── test_email.py      — from catpro/test_email.py
├── scripts/
│   ├── process_claim.py      — CLI entry point (imports services)
│   ├── poll.py               — Poller entry point
│   └── send_test_email.py    — Test email entry point
├── alembic/                   — database migrations
├── alembic.ini
├── requirements.txt
└── pyproject.toml

frontend/
├── src/
│   ├── components/
│   │   ├── layout/           — AppLayout, Sidebar, TopNav
│   │   ├── dashboard/        — SummaryCard, TrendChart
│   │   ├── claims/           — ClaimsTable, ClaimDetail
│   │   ├── filters/          — FilterPanel, DateRange
│   │   └── common/           — DataTable, StatusBadge
│   ├── pages/
│   │   └── Dashboard.tsx
│   ├── hooks/
│   │   └── useClaims.ts      — React Query hooks for API
│   ├── stores/
│   │   ├── uiStore.ts        — sidebar, active sheet
│   │   └── filterStore.ts    — date range, status, search
│   ├── lib/
│   │   ├── api.ts            — Axios instance pointing to FastAPI
│   │   └── utils.ts          — cn(), formatDate, etc.
│   ├── types/
│   │   └── claim.ts          — TypeScript interfaces matching API schemas
│   └── index.css             — Tailwind base + dark theme CSS variables
├── package.json
├── vite.config.ts
├── tailwind.config.js
├── tsconfig.json
└── postcss.config.js

data/                          — shared SQLite database (runtime)
docs/                          — architecture, requirements, brainstorms, plans
```

## Open Questions

- Alembic initial migration: generate from existing SQLite schema or define fresh models and migrate?
- Should scripts/ use `python -m backend.scripts.poll` or standalone entry points in pyproject.toml?
- WebSocket for real-time claim status updates (future)?

## Next Steps

→ `/ce:plan` for implementation details
