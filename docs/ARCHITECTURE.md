# Architecture

Status: proposed, accepted by the user on 2026-10-03 (no objection to the stack). Details can change in P0.

## Stack
- Backend: Python 3.12, FastAPI, SQLAlchemy, SQLite (one file: `data/fantasy.db`).
  - Reason: the useful libraries are in Python (Yahoo API wrappers, `nba_api`, `youtube-transcript-api`, pandas for z-scores).
- Frontend: React + Vite + TypeScript. Charts: one library (choose in P0, for example Recharts or ECharts). Table: TanStack Table.
- Jobs: simple in-process scheduler (APScheduler) for sync and for draft polling.
- LLM: `claude -p` subprocess (see `CLAUDE.md`). Only for M8 and M9.
- One command starts all: `make dev`.

## Folders (planned)
```
backend/
  app/
    api/          # FastAPI routers, one per module
    sources/      # yahoo/, nba/, schedule/, experts/  (read-only clients)
    models/       # DB tables
    analytics/    # valuation, inflation, punt, h2h, trade math (pure functions, tested)
    jobs/         # sync and polling jobs
  tests/
frontend/
  src/
    widgets/      # one folder per widget
    layout/       # dashboard grid, widget registry
    api/          # typed API client
data/             # sqlite db, cached raw responses (git-ignored)
docs/
```

## Data flow
1. `sources/*` fetch raw data. Raw responses are cached in `data/raw/` with a timestamp.
2. `jobs/*` normalize raw data into DB tables.
3. `analytics/*` compute from DB tables. Pure functions, unit tested.
4. `api/*` serve results as JSON.
5. Widgets poll the API (draft board: every 3 s).

## Core tables (first draft)
- `players` (one row per NBA player, with Yahoo player key and NBA id mapping)
- `player_stats` (season or game level, per source)
- `projections` (per source, per season)
- `leagues` (one row per season; Yahoo league key; renew chain)
- `teams`, `managers` (manager is stable across seasons; team is per season)
- `draft_picks` (season, pick no, team, player, cost)
- `transactions` (add, drop, trade; per season)
- `nba_schedule` (game date, home, away)

## Widget model
- A widget = a React component + a registry entry (id, title, default size).
- The dashboard is a grid. The user can choose and place widgets. Layout is saved in local storage.
- Pages: `Draft`, `League`, `Players`, later `Trades`, `Free agents`, `Schedule`, `Experts`.

## Yahoo access
- OAuth 2.0 with a Yahoo developer app. Read scope only (`fspt-r`).
- Tokens are stored in `.env` / local file. Never commit them.
