"""Sync role sources (T-026) into the DB: projected minutes, depth charts, win totals.

Usage: python -m app.jobs.sync_roles [darko|fantasypros|hashtag|vegas ...]   (default: all)

Links to existing players only, with the sync_players Resolver; never creates a
player or changes identity. Run `make players-sync` first.
- darko: by NBA person id (source "nba"); a name match records the NBA id.
- fantasypros: by FantasyPros id; a name match records it.
- hashtag: by name (+ team when two players share a name), every run. No id is
  stored: the page has none, and a stored name would block re-matching after a trade.
Each run replaces the source's rows for the season, so it is idempotent.
"""

import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.jobs.sync_players import Resolver, load_links
from app.models import DepthChartEntry, PlayerMinutesProjection, TeamWinTotal
from app.seasons import CURRENT_SEASON
from app.sources.players.base import SourcePlayer
from app.sources.roles import darko, fantasypros, hashtag, vegas


@dataclass
class Report:
    source: str
    rows: int = 0
    how: Counter = field(default_factory=Counter)
    unmatched: list[str] = field(default_factory=list)

    def summary(self) -> str:
        s = f"{self.source}: {self.rows} rows, matched by {dict(self.how)}"
        return s + (f", {len(self.unmatched)} without a player" if self.unmatched else "")


def _sp(external_id: str, name: str, team: str | None) -> SourcePlayer:
    first, _, last = name.partition(" ")
    return SourcePlayer(external_id=external_id, first_name=first, last_name=last, team=team)


def _link(resolver: Resolver, report: Report, source: str, sp: SourcePlayer, store_id: bool = True):
    player, how = resolver.resolve(source, sp)
    report.how[how] += 1
    if player is None:
        report.unmatched.append(f"{sp.first_name} {sp.last_name} ({sp.team})")
    elif how != "id" and store_id:
        resolver.add(player, source, sp.external_id)
    return player


def write_darko(db: Session, rows: list[darko.DarkoPlayer], season: str, links=None) -> Report:
    now, report = datetime.now(UTC), Report(darko.KEY)
    resolver = Resolver(db, load_links() if links is None else links)
    db.execute(delete(PlayerMinutesProjection).where(
        PlayerMinutesProjection.source == darko.KEY, PlayerMinutesProjection.season == season))
    done: set[int] = set()  # two source rows on one player: the first wins
    for r in rows:
        player = _link(resolver, report, "nba", _sp(r.nba_id, r.name, r.team))
        if player and player.id not in done:
            done.add(player.id)
            db.add(PlayerMinutesProjection(player_pk=player.id, source=darko.KEY, season=season,
                                           team=r.team, mpg=r.mpg, gp=None, extra=r.extra, fetched_at=now))
            report.rows += 1
    return report


def write_fantasypros(db: Session, rows: list[fantasypros.FpPlayer], season: str, links=None) -> Report:
    now, report = datetime.now(UTC), Report(fantasypros.KEY)
    resolver = Resolver(db, load_links() if links is None else links)
    db.execute(delete(PlayerMinutesProjection).where(
        PlayerMinutesProjection.source == fantasypros.KEY, PlayerMinutesProjection.season == season))
    done: set[int] = set()  # two source rows on one player: the first wins
    for r in rows:
        sp = SourcePlayer(external_id=r.fp_id, first_name=r.first_name, last_name=r.last_name, team=r.team)
        player = _link(resolver, report, fantasypros.KEY, sp)
        if player and player.id not in done:
            done.add(player.id)
            db.add(PlayerMinutesProjection(
                player_pk=player.id, source=fantasypros.KEY, season=season, team=r.team, mpg=r.mpg,
                gp=r.gp, extra={**r.extra, "positions": r.positions}, fetched_at=now))
            report.rows += 1
    return report


def write_hashtag(db: Session, rows: list[hashtag.DepthRow], season: str, links=None) -> Report:
    now, report = datetime.now(UTC), Report(hashtag.KEY)
    resolver = Resolver(db, load_links() if links is None else links)
    db.execute(delete(DepthChartEntry).where(
        DepthChartEntry.source == hashtag.KEY, DepthChartEntry.season == season))
    pks: dict[tuple[str, str], int | None] = {}
    for r in rows:
        if (r.name, r.team) not in pks:  # a player listed in two slots counts once
            player = _link(resolver, report, hashtag.KEY, _sp(r.name, r.name, r.team), store_id=False)
            pks[(r.name, r.team)] = player.id if player else None
        db.add(DepthChartEntry(source=hashtag.KEY, season=season, team=r.team, slot=r.slot,
                               depth=r.depth, order=r.order, player_pk=pks[(r.name, r.team)],
                               player_name=r.name, fetched_at=now))
        report.rows += 1
    return report


def write_vegas(db: Session, rows: list[vegas.WinTotal], season: str) -> Report:
    now, report = datetime.now(UTC), Report(vegas.KEY)
    db.execute(delete(TeamWinTotal).where(TeamWinTotal.source == vegas.KEY, TeamWinTotal.season == season))
    for r in rows:
        db.add(TeamWinTotal(source=vegas.KEY, season=season, team=r.team, wins=r.wins,
                            over_odds=r.over_odds, under_odds=r.under_odds, fetched_at=now))
        report.rows += 1
    return report


def sync_one(key: str, season: str = CURRENT_SEASON) -> Report:
    from app.db import SessionLocal

    if key == darko.KEY:
        rows, writer = darko.parse(darko.fetch()), write_darko
    elif key == fantasypros.KEY:
        rows, writer = fantasypros.parse(fantasypros.fetch()), write_fantasypros
    elif key == hashtag.KEY:
        rows, writer = hashtag.parse(hashtag.fetch()), write_hashtag
    elif key in (vegas.KEY, "vegas"):
        rows, writer = vegas.parse(vegas.fetch(), season), write_vegas
    else:
        raise ValueError(f"unknown role source {key}")
    with SessionLocal.begin() as db:
        return writer(db, rows, season)


KEYS = (darko.KEY, fantasypros.KEY, hashtag.KEY, "vegas")


if __name__ == "__main__":
    from app.db import init_db

    init_db()
    for key in sys.argv[1:] or KEYS:
        r = sync_one(key)
        print(r.summary())
        for name in r.unmatched:
            print("  no player:", name)
