"""Replay extension capture files into the drafts, draft_teams, draft_picks tables.

Idempotent: each run replaces the rows of the drafts it ingests.
Usage: python -m app.jobs.ingest_draft [league_id ...]  (default: all capture folders)
"""

import sys
import threading
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.draft import capture
from app.draft.parser import parse_capture_line
from app.draft.state import DraftState, replay
from app.models import Draft, DraftPick, DraftTeam
from app.seasons import CURRENT_SEASON


def build(league_id: str, base: Path = capture.CAPTURE_DIR) -> tuple[DraftState, list[dict], dict]:
    """Replay one draft. Returns (state, rows, team names by id)."""
    rows = list(capture.iter_rows(league_id, base))
    events = [te for te in map(parse_capture_line, rows) if te is not None]
    teams_payload = capture.v3_payload(rows, "teams") or {}
    names = {int(t["id"]): t["teamname"] for t in teams_payload.get("team_list", [])}
    return replay(events), rows, names


def ingest(db: Session, league_id: str, base: Path = capture.CAPTURE_DIR) -> tuple[Draft, DraftState]:
    state, rows, names = build(league_id, base)
    my_team = next((ids[1] for r in rows if (ids := capture.page_ids(r.get("url")))), None)
    times = [datetime.fromisoformat(r["received_at"]) for r in rows if "received_at" in r]

    draft = db.scalar(select(Draft).where(Draft.yahoo_league_id == league_id))
    if draft is None:
        draft = Draft(yahoo_league_id=league_id)
        db.add(draft)
    draft.kind = "league" if league_id == get_settings().yahoo_league_id else "mock"
    draft.season = CURRENT_SEASON
    draft.my_team_id = my_team
    draft.budget = state.budget
    draft.source = "extension"
    draft.capture_dir = str(base / league_id)
    draft.first_event_at = min(times, default=None)
    draft.last_event_at = max(times, default=None)
    draft.ingested_at = datetime.now(UTC)
    db.flush()

    db.execute(delete(DraftTeam).where(DraftTeam.draft_pk == draft.id))
    db.execute(delete(DraftPick).where(DraftPick.draft_pk == draft.id))
    db.add_all(DraftTeam(draft_pk=draft.id, team_id=t, name=n) for t, n in sorted(names.items()))
    db.add_all(
        DraftPick(
            draft_pk=draft.id, pick_no=p.pick_no, team_id=p.team_id, yahoo_player_id=p.player_id,
            price=p.price, roster_slot=p.roster_slot, nominating_team_id=p.nominating_team_id,
            sold_at=p.sold_at,
        )
        for p in sorted(state.picks.values(), key=lambda p: p.pick_no)
    )
    return draft, state


_write_lock = threading.Lock()


def ingest_now(league_id: str, base: Path) -> None:
    """Replay one draft into the DB in its own transaction. Called after each live sale."""
    from app.db import SessionLocal

    with _write_lock, SessionLocal.begin() as db:
        ingest(db, league_id, base)


if __name__ == "__main__":
    from app.db import SessionLocal, init_db

    init_db()
    for lid in sys.argv[1:] or capture.league_ids():
        with SessionLocal.begin() as db:
            d, state = ingest(db, lid)
            print(f"{lid} ({d.kind}): {len(state.picks)} picks, {len(state.warnings)} warnings, "
                  f"unknown messages {state.unknown}")
            for w in state.warnings:
                print("  warning:", w)
