.PHONY: dev backend frontend install test sync yahoo-auth yahoo-check

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
