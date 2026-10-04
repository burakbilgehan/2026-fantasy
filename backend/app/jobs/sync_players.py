"""Sync player sources into players, player_external_ids and the stat tables.

Usage: python -m app.jobs.sync_players [source ...]   (default: all, registry order)

Identity matching is conservative; a wrong merge is worse than a duplicate:
1. Known (source, external id).
2. Manual link in app/sources/players/id_links.json.
3. Same name key, the only player with that name, and no id from this source yet.
4. Several players with that name: the one on the same team without an id
   from this source, if exactly one.
5. Else a new player row.
Each run replaces this source's rows for the synced season, so it is idempotent.
The first source in the registry that lists a player owns its name, team and
position. A player the owner no longer lists gets team None (free agent).
"""

import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    Player, PlayerExternalId, PlayerMarketValue, PlayerProjection, PlayerSeasonStats,
)
from app.seasons import CURRENT_SEASON
from app.sources.players import SOURCES
from app.sources.players.base import SourcePlayer, StatLine, name_key

LINKS_FILE = Path(__file__).resolve().parents[1] / "sources" / "players" / "id_links.json"


def load_links(path: Path = LINKS_FILE) -> dict[tuple[str, str], tuple[str, str]]:
    """{("yahoo", "1234"): ("nba", "5678"), ...} in both directions."""
    links = {}
    for row in json.loads(path.read_text(encoding="utf-8")):
        a, b = tuple(row["a"].split(":", 1)), tuple(row["b"].split(":", 1))
        links[a], links[b] = b, a
    return links


@dataclass
class Report:
    source: str
    how: Counter = field(default_factory=Counter)
    ambiguous: list[str] = field(default_factory=list)  # new rows although the name existed


class Resolver:
    def __init__(self, db: Session, links: dict[tuple[str, str], tuple[str, str]]):
        self.db = db
        self.links = links
        self.players = {p.id: p for p in db.scalars(select(Player))}
        self.ids: dict[tuple[str, str], int] = {}
        self.sources_of: dict[int, set[str]] = defaultdict(set)
        for x in db.scalars(select(PlayerExternalId)):
            self.ids[(x.source, x.external_id)] = x.player_pk
            self.sources_of[x.player_pk].add(x.source)
        self.by_key: dict[str, list[int]] = defaultdict(list)
        for p in self.players.values():
            self.by_key[p.name_key].append(p.id)

    def resolve(self, source: str, sp: SourcePlayer) -> tuple[Player | None, str]:
        if (pk := self.ids.get((source, sp.external_id))) is not None:
            return self.players[pk], "id"
        if (target := self.links.get((source, sp.external_id))) and target in self.ids:
            return self.players[self.ids[target]], "link"
        same_name = self.by_key[name_key(sp.first_name, sp.last_name)]
        free = [pk for pk in same_name if source not in self.sources_of[pk]]
        if len(same_name) == 1 and free:
            return self.players[free[0]], "name"
        same_team = [pk for pk in free if sp.team and self.players[pk].team == sp.team]
        if len(same_team) == 1:
            return self.players[same_team[0]], "name+team"
        return None, "ambiguous" if free else "new"

    def add(self, player: Player, source: str, external_id: str) -> None:
        if player.id not in self.players:
            self.players[player.id] = player
            self.by_key[player.name_key].append(player.id)
        self.db.add(PlayerExternalId(player_pk=player.id, source=source, external_id=external_id))
        self.ids[(source, external_id)] = player.id
        self.sources_of[player.id].add(source)


def _rank(source: str) -> int:
    keys = list(SOURCES)
    return keys.index(source) if source in keys else len(keys)


def _set_identity(p: Player, source: str, sp: SourcePlayer, now: datetime) -> None:
    if p.identity_source and _rank(source) > _rank(p.identity_source):
        return  # a higher-priority source owns name, team and position
    p.first_name, p.last_name = sp.first_name, sp.last_name
    p.name_key = name_key(sp.first_name, sp.last_name)
    p.team, p.position = sp.team, sp.position
    p.identity_source, p.updated_at = source, now


def _stat_row(model, pk: int, source: str, line: StatLine, now: datetime):
    return model(player_pk=pk, source=source, season=line.season, fetched_at=now, **line.stats)


def write(db: Session, source: str, players: list[SourcePlayer], season: str,
          links: dict | None = None) -> Report:
    now = datetime.now(UTC)
    report = Report(source)
    resolver = Resolver(db, load_links() if links is None else links)
    actual_seasons = {line.season for sp in players for line in sp.actual}
    db.execute(delete(PlayerProjection).where(
        PlayerProjection.source == source, PlayerProjection.season == season))
    db.execute(delete(PlayerMarketValue).where(
        PlayerMarketValue.source == source, PlayerMarketValue.season == season))
    db.execute(delete(PlayerSeasonStats).where(
        PlayerSeasonStats.source == source, PlayerSeasonStats.season.in_(actual_seasons)))

    seen: set[int] = set()
    for sp in players:
        player, how = resolver.resolve(source, sp)
        report.how[how] += 1
        if player is None:
            if how == "ambiguous":
                report.ambiguous.append(f"{sp.first_name} {sp.last_name} ({sp.team}) {source}:{sp.external_id}")
            player = Player(identity_source="")
            _set_identity(player, source, sp, now)
            db.add(player)
            db.flush()
        else:
            _set_identity(player, source, sp, now)
        seen.add(player.id)
        if how != "id":
            resolver.add(player, source, sp.external_id)
        if sp.projection:
            db.add(_stat_row(PlayerProjection, player.id, source, sp.projection, now))
        for line in sp.actual:
            db.add(_stat_row(PlayerSeasonStats, player.id, source, line, now))
        if m := sp.market:
            db.add(PlayerMarketValue(
                player_pk=player.id, source=source, season=m.season, auction_value=m.auction_value,
                average_cost=m.average_cost, average_pick=m.average_pick,
                percent_drafted=m.percent_drafted, rank=m.rank, positions=m.positions,
                injury=m.injury, injury_note=m.injury_note, extra=m.extra, fetched_at=now,
            ))
    # Players this source owns but no longer lists (waived, left the league): no team.
    for p in resolver.players.values():
        if p.identity_source == source and p.id not in seen and p.team is not None:
            p.team, p.updated_at = None, now
    return report


def sync(keys: list[str] | None = None, season: str = CURRENT_SEASON) -> list[Report]:
    from app.db import SessionLocal, init_db

    init_db()
    reports = []
    for key in keys or list(SOURCES):
        src = SOURCES[key]
        players = src.parse(src.fetch(), season)
        with SessionLocal.begin() as db:
            reports.append(write(db, key, players, season))
    return reports


if __name__ == "__main__":
    for r in sync(sys.argv[1:] or None):
        print(f"{r.source}: {sum(r.how.values())} players, matched by {dict(r.how)}")
        for line in r.ambiguous:
            print("  ambiguous, new row:", line)
