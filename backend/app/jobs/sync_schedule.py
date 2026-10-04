"""Sync the NBA regular season schedule into nba_schedule.

Usage: python -m app.jobs.sync_schedule [season]   (default: CURRENT_SEASON)
Replaces all ESPN rows of the season, so it is idempotent. Re-run in December,
when the NBA adds the last 2 games per team after the NBA Cup group stage.
"""

import sys
from datetime import UTC, datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import NbaGame
from app.seasons import CURRENT_SEASON
from app.sources.schedule import espn
from app.sources.schedule.espn import Game


def write(db: Session, games: list[Game], season: str) -> None:
    now = datetime.now(UTC)
    db.execute(delete(NbaGame).where(NbaGame.source == "espn", NbaGame.season == season))
    db.add_all(
        NbaGame(
            source="espn", source_game_id=g.source_game_id, season=season, start_utc=g.start_utc,
            game_date_et=g.game_date_et, home=g.home, away=g.away, neutral_site=g.neutral_site,
            fetched_at=now,
        )
        for g in games
    )


def sync(season: str = CURRENT_SEASON) -> list[Game]:
    from app.db import SessionLocal, init_db

    init_db()
    games = espn.parse(espn.fetch(season), season)
    with SessionLocal.begin() as db:
        write(db, games, season)
    return games


if __name__ == "__main__":
    games = sync(*sys.argv[1:2])
    print(f"{len(games)} games, {games[0].game_date_et} to {games[-1].game_date_et}")
