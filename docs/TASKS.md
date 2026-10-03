# Tasks

Status: `todo`, `doing`, `done`, `blocked`. Keep this file current at the end of each session.

## P0 (target 2026-10-08)
| ID | Task | Status | Notes |
|----|------|--------|-------|
| T-001 | Create Yahoo developer app (read scope) with Claude in Chrome. User logs in, Claude fills the form. Save client id/secret in `.env`. | todo | Needs Claude in Chrome in the session (`claude --chrome` or `/chrome`). |
| T-002 | Decide: git repo for this folder (local git + private GitHub repo with gh). | todo | Ask the user. |
| T-003 | Scaffold backend (FastAPI, SQLite) and frontend (Vite React TS). `make dev` starts both. | todo | Show plan first. |
| T-004 | Yahoo OAuth flow and read client. Fetch league 23772 settings, teams, roster size. | todo | Check `~/projects/fantasy-basketball/lib/yahoo/` first. |
| T-005 | Fetch league renew chain. Fetch last season's draftresults. Verify `cost` field. | todo | Update `DATA_SOURCES.md`. |
| T-006 | Check projection sources (Yahoo projected stats, Hashtag Basketball, own model). Decide one. | todo | |
| T-007 | NBA players, last seasons' stats, 2026-27 schedule. Map NBA ids to Yahoo player keys. | todo | |

## P1 (target 2026-10-14)
| ID | Task | Status | Notes |
|----|------|--------|-------|
| T-010 | Valuation engine (z-scores, punt toggles, dollar values). Unit tests. | todo | See `modules/draft.md`. |
| T-011 | Player value table widget. | todo | |
| T-012 | Draft poller (3 to 5 s) + manual entry mode. | todo | |
| T-013 | Inflation and price ranges. | todo | |
| T-014 | Team profiles and punt hints. | todo | |
| T-015 | Manager auction tendencies from last season. | todo | Optional for P1. |

## P2 (target 2026-10-17)
| ID | Task | Status | Notes |
|----|------|--------|-------|
| T-020 | Check if Yahoo mock drafts are visible in the API. Rehearsal with the user. | todo | |
