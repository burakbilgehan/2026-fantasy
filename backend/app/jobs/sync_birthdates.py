"""Fill players.birth_date and players.birth_date_source (sources: app/sources/birthdates.py).

Usage: python -m app.jobs.sync_birthdates

Three passes, each only for existing players (never creates a player):
1. ESPN rosters ("espn"): by ESPN id (player_external_ids source "espn"), else by
   name_key when exactly one player has it and that player has no ESPN id yet.
   A name match does not record the ESPN id: this job writes only the two birth
   date columns, so a wrong name match costs one wrong date, not a wrong id link.
2. ESPN athlete pages ("espn"): players still without an exact date that have an
   ESPN id (free agents, retired players). One call per player.
3. Age fallback ("nba_age"): players still without an exact date that have an
   AGE in player_advanced_stats (latest season). Can be off by up to 6 months.
   Needs `make advanced-stats-sync` first.
An "espn" date is never replaced by an "nba_age" date. Idempotent.
Run after `make players-sync`. Also run by `refresh` (7 day TTL).
"""

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Player, PlayerAdvancedStats, PlayerExternalId, PlayerSeasonStats
from app.seasons import CURRENT_SEASON, previous
from app.sources import birthdates
from app.sources.players.base import name_key

ESPN = "espn"
NBA_AGE = "nba_age"


@dataclass
class Report:
    by_id: int = 0  # roster athletes matched by ESPN id
    by_name: int = 0  # roster athletes matched by unique name_key
    unmatched: int = 0  # roster athletes with no player, or an ambiguous name
    athlete_pages: int = 0  # dates from ESPN athlete pages
    nba_age: int = 0  # approximate dates from stats.nba.com AGE
    last_season: str = ""
    last_season_players: int = 0  # players with stats.nba.com totals in last_season
    last_season_missing: int = 0  # of those, still without a birth date

    def summary(self) -> str:
        return (f"rosters: {self.by_id} by id, {self.by_name} by name, {self.unmatched} unmatched; "
                f"athlete pages: {self.athlete_pages}; nba_age: {self.nba_age}; "
                f"{self.last_season}: {self.last_season_missing} of {self.last_season_players} "
                f"players without a birth date")


def write_espn(db: Session, rows: list[birthdates.EspnBirth], report: Report,
               by_name: bool = True) -> None:
    players = {p.id: p for p in db.scalars(select(Player))}
    espn_ids = dict(db.execute(select(PlayerExternalId.external_id, PlayerExternalId.player_pk)
                               .where(PlayerExternalId.source == ESPN)).all())
    has_espn = set(espn_ids.values())
    by_key: dict[str, list[int]] = defaultdict(list)
    for p in players.values():
        by_key[p.name_key].append(p.id)
    done: set[int] = set()  # two rows on one player: the first wins
    for r in rows:
        if r.birth_date is None:
            continue
        pk, how = espn_ids.get(r.espn_id), "id"
        if pk is None and by_name:
            same = by_key.get(name_key(r.first_name, r.last_name), [])
            pk, how = (same[0], "name") if len(same) == 1 and same[0] not in has_espn else (None, "")
        if pk is None:
            report.unmatched += 1
            continue
        if pk in done:
            continue
        done.add(pk)
        p = players[pk]
        p.birth_date, p.birth_date_source = r.birth_date, ESPN
        if not by_name:
            report.athlete_pages += 1
        elif how == "id":
            report.by_id += 1
        else:
            report.by_name += 1


def missing_espn_ids(db: Session) -> list[str]:
    """ESPN ids of players without an exact birth date."""
    return list(db.scalars(
        select(PlayerExternalId.external_id).join(Player, Player.id == PlayerExternalId.player_pk)
        .where(PlayerExternalId.source == ESPN,
               (Player.birth_date.is_(None)) | (Player.birth_date_source != ESPN))
        .order_by(PlayerExternalId.external_id)))


def write_nba_age(db: Session, report: Report) -> None:
    rows = db.execute(
        select(PlayerAdvancedStats.player_pk, PlayerAdvancedStats.season, PlayerAdvancedStats.extra)
        .join(Player, Player.id == PlayerAdvancedStats.player_pk)
        .where((Player.birth_date.is_(None)) | (Player.birth_date_source != ESPN))
        .order_by(PlayerAdvancedStats.season.desc())).all()
    done: set[int] = set()  # latest season first
    for pk, season, extra in rows:
        age = (extra or {}).get("age")
        if pk in done or age is None:
            continue
        done.add(pk)
        p = db.get(Player, pk)
        p.birth_date, p.birth_date_source = birthdates.approx_birth_date(season, age), NBA_AGE
        report.nba_age += 1


def coverage(db: Session, report: Report, season: str) -> None:
    pks = select(PlayerSeasonStats.player_pk).where(
        PlayerSeasonStats.source == "nba", PlayerSeasonStats.season == season)
    report.last_season = season
    report.last_season_players = db.scalar(select(func.count()).select_from(pks.subquery()))
    report.last_season_missing = db.scalar(select(func.count(Player.id)).where(
        Player.id.in_(pks), Player.birth_date.is_(None)))


def sync() -> Report:
    from app.db import SessionLocal, init_db

    init_db()
    report = Report()
    rows = birthdates.parse_rosters(birthdates.fetch_rosters())
    with SessionLocal.begin() as db:
        write_espn(db, rows, report)
    with SessionLocal() as db:
        ids = missing_espn_ids(db)
    athletes = birthdates.parse_athletes(birthdates.fetch_athletes(ids)) if ids else []
    with SessionLocal.begin() as db:
        write_espn(db, athletes, report, by_name=False)
        db.flush()
        write_nba_age(db, report)
        db.flush()
        coverage(db, report, previous(CURRENT_SEASON))
    return report


if __name__ == "__main__":
    print(sync().summary())
