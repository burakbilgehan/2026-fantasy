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
- Player tables (built, 2026-10-04, T-007). Rule: a new source adds rows, never columns.
  - `players`: identity only (name, normalized `name_key`, team, position). `team` comes from NBA.com when the player is on a roster. Players without an NBA.com id keep the team their source reports, which can be stale for free agents.
  - `player_external_ids`: (player, source, external id). Yahoo id, NBA person id, later others.
  - `player_projections`: season totals per (player, source, season). Columns: gp, fgm, fga, ftm, fta, tpm, pts, reb, ast, stl, blk, tov.
  - `player_season_stats`: actual season totals, same columns. Both tables also have `min` (total minutes, nullable: only sources that have it fill it). Past seasons are rows with another `season`.
  - `player_game_logs`: one row per player per game played (source, season, game id, date, team, opponent, home, minutes, the 11 box score fields). Past seasons from stats.nba.com.
  - `player_game_logs.season_type`: `regular` or `preseason` (migration 0007). Season totals are regular season only.
  - `player_minutes_projections` (T-026): minutes per game from sources without a full stat line (DARKO: no GP; FantasyPros: no shot attempts). Other source fields in `extra`. ESPN minutes stay in `player_projections.min`.
  - `depth_charts` (T-026): one row per player per team slot (source, team, slot, tier `depth`, list `order`, `player_pk` or null). A sync replaces the source's rows.
  - `team_win_totals` (T-026): season win total line per NBA team.
  - `knowledge_tags` (T-022, migration 0008): one row per tag on a player or team profile, after the tag registry and the category check. Rebuilt from the profile JSON on every `make knowledge-run`.
  - `sync_runs`: one row per refresh job run (see "Automatic refresh").
  - `player_market_values`: values a source publishes (Yahoo auction value, average cost, ADP, rank, eligible positions, injury).
  - Values computed by our models get their own table, added with T-010. They never go into the tables above.
  - Totals only. Per-game = total / gp, computed when read.
- `nba_schedule` (built, 2026-10-04): one row per regular season game. Start time in UTC and the US Eastern date.
- `leagues` (one row per season; Yahoo league key; renew chain)
- `teams`, `managers` (manager is stable across seasons; team is per season)
- `drafts`, `draft_teams`, `draft_picks` (built, 2026-10-03): one row per draft seen by the extension (mock or league), its teams, and its picks (pick no, team, Yahoo player id, price, roster slot, nominating team). Past seasons' picks (T-005) go into the same tables later.

## DB migrations
- Alembic, in `backend/migrations/`. `init_db()` runs `upgrade head` on backend start. `make db-upgrade` does the same by hand.
- New table or column: change `app/models`, then `cd backend && uv run alembic revision --autogenerate -m "..."`. Read the generated file before commit.
- A DB made by the old `create_all` (no recorded revision) is stamped automatically on start.

## Draft capture pipeline
1. Extension posts events to `POST /api/capture`. Stored in `data/raw/draft_capture/{league_id}/{YYYYMMDD}.jsonl` (raw files are the source of truth).
2. `app/draft/parser.py` turns WebSocket lines into typed events. `app/draft/state.py` replays them into a draft state (pure, tested).
3. `make draft-ingest` writes the replayed picks into the draft tables. Idempotent.
4. Live (T-012): the capture endpoint also applies each event to an in-memory state per league (`app/draft/live.py`, rebuilt from the files on first use). Each sale runs the same ingest in the background. Frontend reads `GET /api/draft/live/{league_id}` every 3 s.
- Past league drafts: `make past-draft-sync` (`app/jobs/sync_past_draft.py`) reads last season's public draftresults page into the same tables (`drafts.kind = "past_league"`, `drafts.season`). Pick order, team and price only; no nominations, no bids.
- `transactions` (add, drop, trade; per season)

## Player data sources
- Code: `backend/app/sources/players/`. A source implements `PlayerSource` (`base.py`): `fetch()` downloads and saves the raw copy, `parse(raw, season)` returns `SourcePlayer` objects. Sources never touch the DB.
- `app/jobs/sync_players.py` links each `SourcePlayer` to a `players` row and replaces the source's rows for the season. `make players-sync` (all) or `make players-sync SOURCE=yahoo`. API: `GET /api/players/sources`, `GET /api/players?source=yahoo`, `POST /api/players/sync`.
- Identity matching, in order: known source id; manual link in `id_links.json`; unique name; same name and same team. Else a new row. A wrong merge is worse than a duplicate. The job prints ambiguous names: add a link for each real duplicate.
- Registry order = priority. The first source that lists a player owns name, team and position. Now: `nba` (NBA.com roster), `yahoo`, then `espn`.
- Past seasons: `make past-stats-sync` (`app/jobs/sync_past_stats.py`, stats.nba.com totals, default the 3 seasons before `CURRENT_SEASON`). Rows in `player_season_stats` with source `nba`. Links to existing players only (same Resolver); never creates a player or changes identity. Run after `make players-sync`.
- Game logs: `make game-logs-sync` (`app/jobs/sync_game_logs.py`, stats.nba.com `leaguegamelog`, same seasons and same linking rules). Rows in `player_game_logs`.
- Season label: `CURRENT_SEASON` env var, default `2026-27` (`app/seasons.py`).

How to add a source (example: Hashtag Basketball):
1. Check the source terms and URL. Add a row to `DATA_SOURCES.md`.
2. Create `backend/app/sources/players/<name>.py` with a class that has `key`, `label`, `provides`, `fetch()`, `parse()`.
3. In `parse()`, return season totals with the `STAT_FIELDS` keys. Convert per-game numbers: value x gp.
4. Convert team names with `app.sources.teams.canonical()`. Add aliases there if needed.
5. Register the class in `SOURCES` in `backend/app/sources/players/__init__.py`. Put it after `nba`.
6. Add a small gzipped fixture in `backend/tests/fixtures/` and parse tests in `tests/test_players.py`.
7. Run `make players-sync SOURCE=<key>`. Read the ambiguous list. Add links to `id_links.json` where needed.
- No DB change is needed for a new source.

## Role sources (T-026)
- Code: `backend/app/sources/roles/` (`darko.py`, `fantasypros.py`, `hashtag.py`, `vegas.py`). Each has `fetch()` (saves the raw page in `data/raw/<key>/`) and a pure `parse()`. Job: `app/jobs/sync_roles.py`, `make roles-sync` (all) or `make roles-sync SOURCE=hashtag`.
- Links to existing players only (same Resolver as `sync_players`), never creates a player. DARKO by NBA id, FantasyPros by its id (stored after the first name match), Hashtag by name every run (no id stored). A Hashtag name that does not match: add `{"a": "hashtag:<name as on the page>", "b": "nba:<id>"}` to `id_links.json`.
- Run after `make players-sync`.

## Automatic refresh
- `app/jobs/refresh.py`. The backend runs stale jobs on start and then every hour (thread started in the FastAPI lifespan). A job is stale when its last success is older than its TTL. A failed job waits 1 hour before the next try. One failed job does not stop the others.
- Jobs and TTL: `hashtag` 6 h, `darko` 12 h, `fantasypros` 12 h, `vegas` 24 h, `game_logs_current` 6 h (stats.nba.com, preseason and regular season of `CURRENT_SEASON`).
- Not in the loop: `players-sync` (Yahoo feed is on demand only). Run it by hand, also on draft morning.
- `GET /api/sync/status` (last run, last success, stale), `POST /api/sync/refresh?force=`. `make refresh` (`ARGS=--force` runs all). `AUTO_REFRESH=0` in `.env` stops the loop. Tests set it to 0 (`tests/conftest.py`).
- Add a job: a function that returns a one-line summary, then one `Job(...)` line in `JOBS`.

## Expert digest (M8, first part, T-021)
1. `make expert-run`: interactive runner for the user's terminal. Batches of 10 (`BATCH=`). Transcripts are fetched one by one; the LLM calls of a batch run in parallel (`PARALLEL=`, default = batch size). Progress bars, elapsed and remaining time, list price spent and projected. Ctrl-C once: no new videos, running calls finish; twice: kill all running calls. A subscription usage limit stops the run. Defaults: Locked On channel since video HxQjagSTTAM (`EXPERT_URL=`, `EXPERT_SINCE=`). Plain batch command: `make expert-digest URL=<playlist, channel /videos tab, or video>` (optional `SINCE=`, `LIMIT=`, `ARGS=--force`).
2. `app/sources/experts/youtube.py`: video ids (yt-dlp), metadata, transcript. Cache: `data/raw/experts/youtube/{id}.json`. When YouTube blocks caption requests, transcripts come from the user's Chrome through `app/jobs/transcript_receiver.py` into the same cache; then run `make expert-run CACHED_ONLY=1`.
3. `app/experts/extract.py`: one `claude -p` call per video, JSON schema output. Prompts, schema, model and effort: `prompts/expert_digest/` (see its README). `make expert-prompt VIDEO=<id>` prints the exact call. Every note has a timestamp and a verbatim quote.
4. `app/experts/transcript.py`: quote check against the transcript (fuzzy, min 6 words). A note whose quote is not found is `verified: false` and only shows in its video page.
5. Source of truth (in git): `docs/knowledge/_data/videos/{id}.json`. Done videos are skipped unless `PROMPT_VERSION` changes or `--force`.
6. `app/experts/render.py`: markdown in `docs/knowledge/` (videos, players, teams, methods, claims). Player and team pages have two sections: Durable and Current.
7. Names are matched at render time (`app/experts/match.py`): user alias, exact name, learned nickname, then last name and first initial. The note's team decides between players with the same name. Learned nicknames are written to `docs/knowledge/aliases.json` (`learned_players`) and never go into the prompt. Fix a wrong match with a user alias (`players`), then `make expert-render` (no LLM call).

## Valuation (T-017, T-010)
- `app/analytics/valuation/`: pure functions. `run(rows, model, Settings)` gives per player category z, total, rank and dollars. Model registry with the dropdown descriptions: `models.py`. G-score weights from game logs: `gscore.py`. Dollars (plain, SAVOR): `dollars.py`.
- API: `GET /api/valuation/options`, `GET /api/valuation` (`app/api/valuation.py`). Computed per request; no DB table. Widget: `frontend/src/widgets/player-values/`.
- Backtest: `make valuation-backtest` (`app/jobs/valuation_backtest.py`, helpers `app/analytics/h2h_backtest.py`). Writes `docs/modules/valuation-backtest.md`.

## Player drawer (T-028)
- Frontend: `frontend/src/components/PlayerDrawer.tsx` (player id + optional valuation query), `Markdown.tsx` (`marked`, sanitized by `dompurify`).
- API: `app/api/drawer.py` (`/api/players/{id}/card`, `/api/teams/{team}/depth`, `/api/knowledge/articles/{slug}`) and `GET /api/valuation/player/{id}`.
- `app/knowledge/index.py`: profile slug to player id (from the profile JSON), player to articles, and link rewrite (`#player/<id>`). Reads the files on every call.

## Widget model
- A widget = a React component + a registry entry (id, title, default size).
- The dashboard is a grid. The user can choose and place widgets. Layout is saved in local storage.
- Pages: `Draft`, `League`, `Players`, later `Trades`, `Free agents`, `Schedule`, `Experts`.

## Yahoo access
- OAuth 2.0 with a Yahoo developer app. Read scope only (`fspt-r`).
- Tokens are stored in `.env` / local file. Never commit them.
