"""Fetch past season totals from stats.nba.com into player_season_stats (source "nba").

Usage: python -m app.jobs.sync_past_stats [season ...]   (default: the 3 seasons before CURRENT_SEASON)

Links rows to existing players only, with the sync_players Resolver (NBA id,
manual link, unique name, name + team). A name match records the NBA id.
Never creates a player and never changes name, team or position: the feed has
retired players, and players.team is this season's team. Unmatched rows are
counted and skipped. Run `make players-sync` first. Replaces the "nba" rows of
the synced seasons, so it is idempotent.
"""

import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.jobs.sync_players import Resolver, load_links
from app.models import PlayerSeasonStats
from app.seasons import CURRENT_SEASON, previous
from app.sources.players.base import SourcePlayer
from app.sources.players.nba_stats import NbaStats

SOURCE = NbaStats.key


def default_seasons(current: str = CURRENT_SEASON, n: int = 3) -> list[str]:
    seasons, s = [], current
    for _ in range(n):
        s = previous(s)
        seasons.append(s)
    return sorted(seasons)


@dataclass
class Report:
    seasons: list[str]
    how: Counter = field(default_factory=Counter)
    rows: Counter = field(default_factory=Counter)  # season -> stat rows written
    skipped: Counter = field(default_factory=Counter)  # season -> rows without a player


def write(db: Session, players: list[SourcePlayer], seasons: list[str],
          links: dict | None = None) -> Report:
    now = datetime.now(UTC)
    report = Report(seasons)
    resolver = Resolver(db, load_links() if links is None else links)
    db.execute(delete(PlayerSeasonStats).where(
        PlayerSeasonStats.source == SOURCE, PlayerSeasonStats.season.in_(seasons)))
    for sp in players:
        player, how = resolver.resolve(SOURCE, sp)
        report.how[how] += 1
        lines = [line for line in sp.actual if line.season in seasons]
        if player is None:
            for line in lines:
                report.skipped[line.season] += 1
            continue
        if how != "id":
            resolver.add(player, SOURCE, sp.external_id)
        for line in lines:
            db.add(PlayerSeasonStats(player_pk=player.id, source=SOURCE, season=line.season,
                                     fetched_at=now, **line.stats))
            report.rows[line.season] += 1
    return report


def sync(seasons: list[str] | None = None) -> Report:
    from app.db import SessionLocal, init_db

    init_db()
    seasons = sorted(seasons or default_seasons())
    src = NbaStats()
    players = src.parse(src.fetch(seasons))
    with SessionLocal.begin() as db:
        return write(db, players, seasons)


if __name__ == "__main__":
    r = sync(sys.argv[1:] or None)
    print(f"nba stats {', '.join(r.seasons)}: players matched by {dict(r.how)}")
    for s in r.seasons:
        print(f"  {s}: {r.rows[s]} rows written, {r.skipped[s]} skipped (no player in our DB)")
