.PHONY: dev backend frontend install test sync yahoo-auth yahoo-check draft-ingest db-upgrade players-sync schedule-sync past-draft-sync past-stats-sync game-logs-sync game-logs-current roles-sync refresh expert-digest expert-render expert-prompt expert-run

# Start backend (:8000) and frontend (:5173). Ctrl-C stops both.
dev:
	@trap 'kill 0' INT TERM EXIT; \
	$(MAKE) backend & \
	$(MAKE) frontend & \
	wait

backend:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

install:
	cd backend && uv sync
	cd frontend && npm install

test:
	cd backend && uv run pytest -q

sync:
	cd backend && uv run python -m app.jobs.sync_league

yahoo-auth:
	cd backend && uv run python -m app.sources.yahoo.cli auth

yahoo-check:
	cd backend && uv run python -m app.sources.yahoo.cli check

# Replay extension captures into the draft tables (all folders, or LEAGUE=2600009).
draft-ingest:
	cd backend && uv run python -m app.jobs.ingest_draft $(LEAGUE)

# Apply DB migrations (also runs on backend start).
db-upgrade:
	cd backend && uv run alembic upgrade head

# Fetch player sources into the DB (all, or SOURCE=yahoo). On demand only.
players-sync:
	cd backend && uv run python -m app.jobs.sync_players $(SOURCE)

# Fetch the NBA regular season schedule (ESPN). Re-run in December (NBA Cup games).
schedule-sync:
	cd backend && uv run python -m app.jobs.sync_schedule

# Fetch last season's auction results from the public league pages (prices per pick).
past-draft-sync:
	cd backend && uv run python -m app.jobs.sync_past_draft

# Fetch past season totals from stats.nba.com (default: last 3 seasons, or SEASONS="2024-25 2025-26").
past-stats-sync:
	cd backend && uv run python -m app.jobs.sync_past_stats $(SEASONS)

# Fetch past season game logs from stats.nba.com (default: last 3 seasons, or SEASONS="2025-26"). Run after past-stats-sync.
game-logs-sync:
	cd backend && uv run python -m app.jobs.sync_game_logs $(SEASONS)

# Current season game logs from stats.nba.com: preseason and regular season so far. Also run by `refresh`.
game-logs-current:
	cd backend && uv run python -m app.jobs.sync_game_logs --current

# Role sources (T-026): DARKO and FantasyPros minutes, Hashtag depth charts, Vegas win totals.
# All, or SOURCE=hashtag. Also run by `refresh`. Run after players-sync.
roles-sync:
	cd backend && uv run python -m app.jobs.sync_roles $(SOURCE)

# Run the refresh jobs that are stale (the backend also does this on start and every hour).
# ARGS=--force runs all jobs. Status: GET /api/sync/status. AUTO_REFRESH=0 in .env stops the loop.
refresh:
	cd backend && uv run python -m app.jobs.refresh $(ARGS)

# Expert digest: playlist/channel/video URL -> notes in docs/knowledge/ (claude -p, subscription).
# Optional: SINCE=<video id> (channel /videos tab: that video and newer), LIMIT=5 (new videos per run), ARGS=--force. Re-render markdown only: make expert-render
expert-digest:
	cd backend && uv run python -m app.jobs.digest_experts "$(URL)" $(if $(SINCE),--since $(SINCE)) $(if $(LIMIT),--limit $(LIMIT)) $(ARGS)

expert-render:
	cd backend && uv run python -m app.jobs.digest_experts --render

# Print the exact claude command and prompt for one video: make expert-prompt VIDEO=tnzmsYUA4yQ
expert-prompt:
	cd backend && uv run python -m app.jobs.digest_experts --show-prompt $(VIDEO)

# Interactive runner with progress bars. LLM calls of a batch run in parallel (PARALLEL=, default BATCH).
# Ctrl-C once: no new videos, running ones finish; twice: kill running calls.
# CACHED_ONLY=1: use only cached transcripts (no YouTube transcript requests).
# Defaults: Locked On Fantasy Basketball channel, from video HxQjagSTTAM, batches of 10.
EXPERT_URL ?= https://www.youtube.com/@LockedOnFantasyBasketball/videos
EXPERT_SINCE ?= HxQjagSTTAM
BATCH ?= 10
expert-run:
	@cd backend && uv sync -q && .venv/bin/python -m app.jobs.expert_run "$(EXPERT_URL)" --since $(EXPERT_SINCE) --batch $(BATCH) $(if $(PARALLEL),--parallel $(PARALLEL)) $(if $(CACHED_ONLY),--cached-only)
