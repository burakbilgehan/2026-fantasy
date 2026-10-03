# Tasks

Status: 🔴 blocked, 🟡 todo, 🟩 doing, ✅ done. Keep this file current at the end of each session.

## P0 (target 2026-10-08)
| ID | Task | Status | Notes |
|----|------|--------|-------|
| T-001 | Create Yahoo developer app (read scope) with Claude in Chrome. User logs in, Claude fills the form. Save client id/secret in `.env`. | ✅ done | App `2026-fantasy-read` (GYvitLgi), Fantasy Sports Read. Token in `data/yahoo_token.json`. Old app `2026-fantasy-local` deleted by the user. |
| T-008 | USER: submit Yahoo Fantasy API access application. | ✅ done | Submitted 2026-10-03. Waiting for Yahoo. Check with `make yahoo-check`. Top risk for the draft. API returns 403 until Yahoo approves. Approval time unknown. Draft text: `docs/yahoo-api-access-application.md`. |
| T-009 | Plan B for live draft data: local Chrome extension (unpacked, no Web Store). | 🟩 doing | Yahoo review takes 1 to 2 weeks (Yahoo reply, 2026-10-03), so the API may not be ready by 2026-10-18. The extension reads the draft room in the user's own logged-in tab and posts to `localhost:8000`. Read-only: no clicks, nothing sent to Yahoo. Extension v0.2 (`extension/`, draftclient pages only, Yahoo Fantasy calls only, DOM snapshot every 5 min) and `POST /api/capture` (raw JSON lines in `data/raw/draft_capture/`). Done when T-009b and T-009c are done. |
| T-009a | Capture one Yahoo mock auction draft. Find the data source (WebSocket, XHR or DOM). | ✅ done | Mock 2600009, 2026-10-03. Source = draft room WebSocket (push, browser to backend 26 ms median). Reconnect sends all past picks (`P|`) and budgets (`$|`). Bid history only while the extension runs. Draft client also loads `fantasy/v3/players` (707 players, Yahoo projections, auction value, avg cost). Message format: `docs/modules/draft.md`. Capture: `data/raw/draft_capture/20261003.jsonl`. |
| T-009b | Backend parser + draft state model from WebSocket events (picks, bids, budgets, nomination order). Unit tests with the 2026-10-03 capture as fixture. | 🟡 todo | Reference: `backend/scripts/mock_report.py` (ad hoc). Test fixture: `backend/tests/fixtures/draft_capture_mock_2600009.jsonl.gz` (WebSocket + v3 players/teams/settings/draftstatus, 76 picks, filtered from the raw capture). Same work as the ingest part of T-012. |
| T-009c | Second mock draft, end to end. Also: decode `A|`, `5|`, `H|` messages by comparing with the screen; check the service worker never sleeps through events; then drop DOM snapshots. | 🟡 todo | |
| T-009d | Check if `/nba/23772/draftresults` (public page, no login) updates live during a draft. | 🟡 todo | Low value now. Optional. |
| T-002 | Git repo: local git + private GitHub repo. | ✅ done | https://github.com/burakbilgehan/2026-fantasy |
| T-003 | Scaffold backend (FastAPI, SQLite) and frontend (Vite React TS). `make dev` starts both. | ✅ done | `make dev`, `make test`, `make sync`. Ctrl-C stops both (verified). |
| T-004 | Yahoo OAuth flow and read client. Fetch league 23772 settings, teams, roster size. | 🟩 doing | OAuth + refresh verified live. API client written, blocked by 403 (T-008). Settings and teams come from public pages (verified, shown in UI). API JSON parsers are not verified. Re-auth: `make yahoo-auth`. Check: `make yahoo-check`. |
| T-005 | Fetch league renew chain. Fetch last season's draftresults. Verify `cost` field. | 🟡 todo | Update `DATA_SOURCES.md`. |
| T-006 | Check projection sources (Yahoo projected stats, Hashtag Basketball, own model). Decide one. | 🟡 todo | |
| T-007 | NBA players, last seasons' stats, 2026-27 schedule. Map NBA ids to Yahoo player keys. | 🟡 todo | |

## P1 (target 2026-10-14)
| ID | Task | Status | Notes |
|----|------|--------|-------|
| T-010 | Valuation engine (z-scores, punt toggles, dollar values). Unit tests. | 🟡 todo | See `modules/draft.md`. |
| T-011 | Player value table widget. | 🟡 todo | |
| T-012 | Draft data ingest: API poller (3 to 5 s) when approved, else extension feed (T-009). No manual entry mode (user decision, 2026-10-03). | 🟡 todo | |
| T-013 | Inflation and price ranges. | 🟡 todo | |
| T-014 | Team profiles and punt hints. | 🟡 todo | |
| T-015 | Manager auction tendencies from last season. | 🟡 todo | Optional for P1. |

## P2 (target 2026-10-17)
| ID | Task | Status | Notes |
|----|------|--------|-------|
| T-020 | Check if Yahoo mock drafts are visible in the API. Rehearsal with the user. | 🟡 todo | |
