# Tasks

Status: 🔴 blocked, 🟡 todo, 🟩 doing, ✅ done. Keep this file current at the end of each session.

## P0 (target 2026-10-08)
| ID | Task | Status | Notes |
|----|------|--------|-------|
| T-001 | Create Yahoo developer app (read scope) with Claude in Chrome. User logs in, Claude fills the form. Save client id/secret in `.env`. | ✅ done | App `2026-fantasy-read` (GYvitLgi), Fantasy Sports Read. Token in `data/yahoo_token.json`. Old app `2026-fantasy-local` deleted by the user. |
| T-008 | USER: submit Yahoo Fantasy API access application. | ✅ done | Submitted 2026-10-03. Waiting for Yahoo. Check with `make yahoo-check`. Top risk for the draft. API returns 403 until Yahoo approves. Approval time unknown. Draft text: `docs/yahoo-api-access-application.md`. |
| T-009 | Plan B for live draft data: local Chrome extension (unpacked, no Web Store). | ✅ done | 2026-10-04. Extension reads the draft room WebSocket in the user's own logged-in tab and posts to `localhost:8000`. Read-only: no clicks, nothing sent to Yahoo. Parser, state model and message decode: T-009b, T-009c. Live use in the app: T-012. |
| T-009a | Capture one Yahoo mock auction draft. Find the data source (WebSocket, XHR or DOM). | ✅ done | Mock 2600009, 2026-10-03. Source = draft room WebSocket (push, browser to backend 26 ms median). Reconnect sends all past picks (`P|`) and budgets (`$|`). Bid history only while the extension runs. Draft client also loads `fantasy/v3/players` (707 players, Yahoo projections, auction value, avg cost). Message format: `docs/modules/draft.md`. Capture: `data/raw/draft_capture/2600009/20261003.jsonl`. |
| T-009b | Backend parser + draft state model from WebSocket events (picks, bids, budgets, nomination order). Unit tests with the 2026-10-03 capture as fixture. | ✅ done | 2026-10-03. `app/draft/parser.py`, `app/draft/state.py`, tests `tests/test_draft.py`. Handles reconnect (`P\|` replay, `b\|` + `D\|` snapshot). Capture now split per draft: `data/raw/draft_capture/{league_id}/`. `make draft-ingest` writes `drafts`, `draft_teams`, `draft_picks`. Bids are kept in memory only, not in the DB (user decision, 2026-10-03: no bid table). |
| T-009c | Second mock draft, end to end. Also: decode `A\|`, `5\|`, `H\|` messages by comparing with the screen; check the service worker never sleeps through events; then drop DOM snapshots. | ✅ done | 2026-10-04. Mock 2600536 (41 picks, 0 warnings), fixture `tests/fixtures/draft_capture_mock_2600536.jsonl.gz`. Verified with the user's screen: `5` autopick on, `6` autopick off; autopick also bids. `X` = own-team timeout notice (inferred). No gap over 8 s in 20 min (service worker stayed awake); a full 1 to 2 hour run is checked in T-020. Extension v0.3: DOM snapshots removed. Still unknown, no state effect: `w`, `Q`, `scout`, `H` field 4. |
| T-009d | Check if `/nba/23772/draftresults` (public page, no login) updates live during a draft. | 🟡 todo | Low value now. Optional. |
| T-002 | Git repo: local git + private GitHub repo. | ✅ done | https://github.com/burakbilgehan/2026-fantasy |
| T-003 | Scaffold backend (FastAPI, SQLite) and frontend (Vite React TS). `make dev` starts both. | ✅ done | `make dev`, `make test`, `make sync`. Ctrl-C stops both (verified). |
| T-016 | DB migrations with Alembic. | ✅ done | 2026-10-03. `backend/migrations/`, runs on backend start, `make db-upgrade`. How to add a table: `ARCHITECTURE.md`. |
| T-004 | Yahoo OAuth flow and read client. Fetch league 23772 settings, teams, roster size. | 🟩 doing | OAuth + refresh verified live. API client written, blocked by 403 (T-008). Settings and teams come from public pages (verified, shown in UI). API JSON parsers are not verified. Re-auth: `make yahoo-auth`. Check: `make yahoo-check`. |
| T-019 | Past seasons player stats (2 to 3 seasons) into `player_season_stats`. Find a reachable source. | ✅ done | 2026-10-04. stats.nba.com through `curl_cffi` (Chrome TLS fingerprint). `make past-stats-sync`: 2023-24, 2024-25, 2025-26 totals, source `nba`. Rows written: 398, 483, 578. Skipped rows have no player in our DB (retired or not in the Yahoo feed): 174, 86, 4. 99 players got their NBA id by unique name. 2025-26 matches Yahoo `season_stats` for 578 of 578 players. Not done: playoffs, seasons before 2023-24. |
| T-005 | Last season's auction prices: fetch the league renew chain and last season's draft results (player, team, price). Verify the `cost` field. | ✅ done | 2026-10-04. Public pages, no login. 2025-26 league 38073: 144 picks with price into `draft_picks` (`drafts.kind = "past_league"`, new column `drafts.season`, migration 0004). `make past-draft-sync`. All 144 player ids match our Yahoo player ids. Team ids are the same as this season. Not done: seasons before 2025-26 (no public link; snake drafts, no prices). API `cost` field still untested (403). |
| T-006 | Source adapter layer for player data (projections, stats, values). First adapter: Yahoo player data loaded by the draft client (`fantasy/v3/players`). | ✅ done | 2026-10-04. `app/sources/players/`: `PlayerSource` interface, Yahoo feed adapter (public URL, no login), NBA.com id adapter. `make players-sync`, `GET /api/players?source=`, `GET /api/players/sources`. Steps to add a source: `ARCHITECTURE.md`. Not done: the source picker in the UI (goes with T-011). |
| T-007 | Player identity table plus separate stat tables (projections, actual season stats, past seasons). Map NBA ids to Yahoo player ids. 2026-27 NBA schedule. | ✅ done | 2026-10-04. Migration 0003: `players`, `player_external_ids`, `player_projections`, `player_season_stats` (past seasons = rows), `player_market_values`, `nba_schedule`. 586 of 707 Yahoo players have an NBA id; the other 121 are not on an NBA.com roster. Schedule: ESPN, 1200 games, `make schedule-sync`; re-run in December (NBA Cup adds 2 games per team). Not done: model values table (T-010). Past seasons: done in T-019. |

## Product research
| ID | Task | Status | Notes |
|----|------|--------|-------|
| T-017 | Player valuation research: how to value a player in this league. Survey existing models and expert methods, test on our data, choose the models the tool offers. | 🟡 todo | Product, big. Own sessions, no parallel work. See `VISION.md`, Player valuation. |
| T-018 | Live draft board refinement: decide what the board, the nominated player panel and market tracking show. | 🟡 todo | Product. See `VISION.md`, Live draft board. |

## P1 (target 2026-10-14)
| ID | Task | Status | Notes |
|----|------|--------|-------|
| T-010 | Valuation engine: code for the models chosen in T-017. Unit tests. | 🟡 todo | Waits for T-017. |
| T-011 | Player value table widget. | 🟡 todo | |
| T-012 | Draft data ingest: API poller (3 to 5 s) when approved, else extension feed (T-009). No manual entry mode (user decision, 2026-10-03). | 🟡 todo | |
| T-013 | Price ranges and market tracking during the draft. | 🟡 todo | Product. Needs a refinement session (`VISION.md`, Live draft board). |
| T-014 | Team profiles and punt hints. | 🟡 todo | |
| T-015 | Manager auction tendencies from last season. | 🟡 todo | Optional for P1. |

## P2 (target 2026-10-17)
| ID | Task | Status | Notes |
|----|------|--------|-------|
| T-020 | Check if Yahoo mock drafts are visible in the API. Rehearsal with the user. | 🟡 todo | |
