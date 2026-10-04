"""Fetch advanced season stats (usage rate) from stats.nba.com into player_advanced_stats.

Usage: python -m app.jobs.sync_advanced_stats [season ...]   (default: the 3 seasons before CURRENT_SEASON)

Links by NBA person id only (recorded by players-sync and past-stats-sync). Rows of
unknown ids are skipped. Replaces the synced seasons' rows, so it is idempotent.
"""

import sys
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.jobs.sync_past_stats import default_seasons
from app.models import PlayerAdvancedStats, PlayerExternalId
from app.sources.players import nba_advanced

SOURCE = "nba"


def write(db: Session, rows: list[dict], seasons: list[str]) -> tuple[Counter, Counter]:
    now = datetime.now(UTC)
    ids = dict(db.execute(select(PlayerExternalId.external_id, PlayerExternalId.player_pk)
                          .where(PlayerExternalId.source == SOURCE)).all())
    db.execute(delete(PlayerAdvancedStats).where(
        PlayerAdvancedStats.source == SOURCE, PlayerAdvancedStats.season.in_(seasons)))
    written, skipped = Counter(), Counter()
    for r in rows:
        if r["season"] not in seasons:
            continue
        pk = ids.get(r["nba_id"])
        if pk is None:
            skipped[r["season"]] += 1
            continue
        db.add(PlayerAdvancedStats(player_pk=pk, source=SOURCE, season=r["season"], gp=r["gp"],
                                   usg_pct=r["usg_pct"], ts_pct=r["ts_pct"], extra=r["extra"], fetched_at=now))
        written[r["season"]] += 1
    return written, skipped


def sync(seasons: list[str] | None = None) -> tuple[list[str], Counter, Counter]:
    from app.db import SessionLocal, init_db

    init_db()
    seasons = sorted(seasons or default_seasons())
    rows = nba_advanced.parse(nba_advanced.fetch(seasons))
    with SessionLocal.begin() as db:
        written, skipped = write(db, rows, seasons)
    return seasons, written, skipped


if __name__ == "__main__":
    seasons, written, skipped = sync(sys.argv[1:] or None)
    for s in seasons:
        print(f"  {s}: {written[s]} rows written, {skipped[s]} skipped (no NBA id in our DB)")
