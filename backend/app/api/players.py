from datetime import UTC

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from app.db import SessionLocal
from app.jobs import sync_players
from app.models import (
    Player, PlayerExternalId, PlayerMarketValue, PlayerProjection, PlayerSeasonStats,
)
from app.seasons import CURRENT_SEASON, previous
from app.sources.players import SOURCES
from app.sources.players.base import STAT_FIELDS

router = APIRouter(prefix="/api/players")


def _stats(row) -> dict | None:
    return {f: getattr(row, f) for f in STAT_FIELDS} if row else None


@router.get("/sources")
def get_sources() -> list[dict]:
    """Registered sources, for the UI source picker."""
    with SessionLocal() as db:
        synced = dict(db.execute(
            select(PlayerProjection.source, func.max(PlayerProjection.fetched_at))
            .group_by(PlayerProjection.source)
        ).all())
        counts = dict(db.execute(
            select(PlayerExternalId.source, func.count()).group_by(PlayerExternalId.source)
        ).all())
    return [
        {
            "key": s.key, "label": s.label, "provides": list(s.provides),
            "players": counts.get(s.key, 0),
            "projections_synced_at": t.replace(tzinfo=UTC).isoformat() if (t := synced.get(s.key)) else None,
        }
        for s in SOURCES.values()
    ]


@router.get("")
def get_players(source: str = "yahoo", season: str = CURRENT_SEASON) -> list[dict]:
    """Players with a projection from `source`. Stats are season totals (per-game = total / gp)."""
    if source not in SOURCES:
        raise HTTPException(404, f"Unknown source {source}. See /api/players/sources")
    with SessionLocal() as db:
        actual = {
            r.player_pk: r for r in db.scalars(select(PlayerSeasonStats).where(
                PlayerSeasonStats.source == source, PlayerSeasonStats.season == previous(season)))
        }
        market = {
            r.player_pk: r for r in db.scalars(select(PlayerMarketValue).where(
                PlayerMarketValue.source == source, PlayerMarketValue.season == season))
        }
        rows = db.execute(
            select(Player, PlayerProjection)
            .join(PlayerProjection, PlayerProjection.player_pk == Player.id)
            .where(PlayerProjection.source == source, PlayerProjection.season == season)
        ).all()
        out = []
        for p, proj in rows:
            m = market.get(p.id)
            out.append({
                "player_id": p.id, "name": f"{p.first_name} {p.last_name}", "team": p.team,
                "positions": m.positions if m else None,
                "injury": m.injury if m else None,
                "projection": _stats(proj),
                "previous_season": _stats(actual.get(p.id)),
                "market": {
                    "auction_value": m.auction_value, "average_cost": m.average_cost,
                    "average_pick": m.average_pick, "rank": m.rank,
                } if m else None,
            })
    out.sort(key=lambda r: (r["market"] or {}).get("rank") or 10**6)
    return out


@router.post("/sync")
def post_sync(source: str | None = None) -> list[dict]:
    """Fetch now. On demand only (the Yahoo feed is undocumented; no timer)."""
    if source is not None and source not in SOURCES:
        raise HTTPException(404, f"Unknown source {source}")
    reports = sync_players.sync([source] if source else None)
    return [{"source": r.source, "matched_by": dict(r.how), "ambiguous": r.ambiguous} for r in reports]
