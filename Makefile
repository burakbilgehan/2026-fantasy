.PHONY: dev backend frontend install test sync yahoo-auth yahoo-check draft-ingest db-upgrade players-sync schedule-sync

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
