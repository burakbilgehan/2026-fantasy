"""Fetch past season game logs from stats.nba.com into player_game_logs (source "nba").

Usage: python -m app.jobs.sync_game_logs [season ...]   (default: the 4 seasons before CURRENT_SEASON)
       python -m app.jobs.sync_game_logs --current        (CURRENT_SEASON: preseason and regular season so far)

Same linking rules as sync_past_stats: existing players only, never creates a
player or changes identity. Unmatched players are counted and skipped. Run
`make players-sync` first. Replaces the "nba" rows of the synced seasons and
season type, so it is idempotent.
"""

import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import delete, insert
from sqlalchemy.orm import Session

from app.jobs.sync_past_stats import default_seasons
from app.jobs.sync_players import Resolver, load_links
from app.models import PlayerGameLog
from app.seasons import CURRENT_SEASON
from app.sources.players.base import SourcePlayer
from app.sources.players.nba_gamelog import GameLine, NbaGameLog

SOURCE = NbaGameLog.key


@dataclass
class Report:
    seasons: list[str]
    how: Counter = field(default_factory=Counter)
    rows: Counter = field(default_factory=Counter)  # season -> game rows written
    skipped: Counter = field(default_factory=Counter)  # season -> game rows without a player


def write(db: Session, players: list[tuple[SourcePlayer, list[GameLine]]], seasons: list[str],
          links: dict | None = None, season_type: str = "regular") -> Report:
    now = datetime.now(UTC)
    report = Report(seasons)
    resolver = Resolver(db, load_links() if links is None else links)
    db.execute(delete(PlayerGameLog).where(
        PlayerGameLog.source == SOURCE, PlayerGameLog.season.in_(seasons),
        PlayerGameLog.season_type == season_type))
    rows = []
    for sp, games in players:
        player, how = resolver.resolve(SOURCE, sp)
        report.how[how] += 1
        games = [g for g in games if g.season in seasons]
        if player is None:
            for g in games:
                report.skipped[g.season] += 1
            continue
        if how != "id":
            resolver.add(player, SOURCE, sp.external_id)
        for g in games:
            rows.append(dict(player_pk=player.id, source=SOURCE, season=g.season,
                             season_type=season_type, game_id=g.game_id,
                             game_date=g.game_date, team=g.team, opponent=g.opponent, home=g.home,
                             fetched_at=now, **g.stats))
            report.rows[g.season] += 1
    db.flush()  # new external ids first
    if rows:
        db.execute(insert(PlayerGameLog), rows)
    return report


def sync(seasons: list[str] | None = None, season_type: str = "regular") -> Report:
    """Completed seasons. The full-season row check applies."""
    from app.db import SessionLocal, init_db

    init_db()
    seasons = sorted(seasons or default_seasons())
    src = NbaGameLog()
    players = src.parse(src.fetch(seasons, season_type))
    with SessionLocal.begin() as db:
        return write(db, players, seasons, season_type=season_type)


def sync_current(season: str = CURRENT_SEASON) -> dict[str, Report]:
    """The season in progress: preseason and regular season games played so far. No row check."""
    from app.db import SessionLocal, init_db

    init_db()
    src = NbaGameLog()
    out = {}
    for season_type in ("preseason", "regular"):
        players = src.parse(src.fetch([season], season_type), min_rows=0)
        with SessionLocal.begin() as db:
            out[season_type] = write(db, players, [season], season_type=season_type)
    return out


def _print(label: str, r: Report) -> None:
    print(f"nba game logs {label} {', '.join(r.seasons)}: players matched by {dict(r.how)}")
    for s in r.seasons:
        print(f"  {s}: {r.rows[s]} games written, {r.skipped[s]} skipped (no player in our DB)")


if __name__ == "__main__":
    if sys.argv[1:] == ["--current"]:
        for season_type, r in sync_current().items():
            _print(season_type, r)
    else:
        _print("regular", sync(sys.argv[1:] or None))
