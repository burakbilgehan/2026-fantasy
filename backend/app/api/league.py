from datetime import UTC

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.jobs.sync_league import sync_league
from app.models import League, Team

router = APIRouter(prefix="/api/league")


def _serialize(db, league: League) -> dict:
    teams = db.scalars(select(Team).where(Team.league_pk == league.id).order_by(Team.team_id))
    return {
        "league_id": league.league_id,
        "name": league.name,
        "num_teams": league.num_teams,
        "scoring_type": league.scoring_type,
        "draft_type": league.draft_type,
        "draft_budget": league.draft_budget,
        "draft_time": league.draft_time,
        "roster_positions": league.roster_positions,
        "stat_categories": league.stat_categories,
        "source": league.source,
        # SQLite drops tzinfo. Values are written in UTC.
        "synced_at": league.synced_at.replace(tzinfo=UTC).isoformat(),
        "teams": [{"team_id": t.team_id, "name": t.name} for t in teams],
    }


@router.get("")
def get_league() -> dict:
    with SessionLocal() as db:
        league = db.scalar(select(League).where(League.league_id == get_settings().yahoo_league_id))
        if league is None:
            raise HTTPException(404, "League not synced yet. POST /api/league/sync")
        return _serialize(db, league)


@router.post("/sync")
def post_sync() -> dict:
    sync_league()
    return get_league()
