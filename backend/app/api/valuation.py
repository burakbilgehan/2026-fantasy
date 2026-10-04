"""Player values (T-010). Spec: docs/modules/valuation.md.

Values are computed on every request from the base rows (fast: under 0.1 s). Nothing is stored.
"""

from functools import lru_cache

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from app.analytics.valuation import BASES, CATEGORIES, MODELS, Settings, g_weights, run
from app.db import SessionLocal
from app.models import League, Player, PlayerGameLog, PlayerMarketValue, PlayerProjection, PlayerSeasonStats
from app.seasons import CURRENT_SEASON
from app.sources.players.base import STAT_FIELDS

router = APIRouter(prefix="/api/valuation")

KINDS = {"projection": PlayerProjection, "actual": PlayerSeasonStats}
DOLLARS = {
    "plain": "Value above replacement level. All drafted players share the league budget.",
    "savor": "Like plain, but cheap players are worth less because waivers replace them. Stars get more.",
}
# User decisions 2026-10-04: default model Minus-1, default pool 200.
DEFAULTS = {"kind": "projection", "source": "espn", "season": CURRENT_SEASON, "basis": "totals",
            "model": "minus1", "dollars": "plain", "pool": 200, "spread": 10.0}
NON_DRAFT_SLOTS = {"IL", "IL+", "NA"}


def _league_draft() -> tuple[int, float]:
    """(players drafted, total budget) from the league settings. Fallback: 12 x 12, 12 x 200."""
    with SessionLocal() as db:
        lg = db.scalar(select(League).order_by(League.synced_at.desc()))
    if not lg:
        return 144, 2400.0
    slots = sum(1 for p in lg.roster_positions if p not in NON_DRAFT_SLOTS)
    return lg.num_teams * slots, float(lg.num_teams * (lg.draft_budget or 200))


@lru_cache(maxsize=8)
def _g_weights(season: str) -> tuple[tuple[str, ...], dict[str, float]]:
    """Weights from the two regular seasons before `season`. No earlier logs: the two oldest seasons."""
    with SessionLocal() as db:
        have = sorted(db.scalars(select(PlayerGameLog.season).where(PlayerGameLog.season_type == "regular").distinct()))
        use = tuple([s for s in have if s < season][-2:] or have[:2])
        cols = ("min", "fgm", "fga", "ftm", "fta", "tpm", "pts", "reb", "ast", "stl", "blk", "tov")
        rows = db.execute(select(PlayerGameLog.player_pk, PlayerGameLog.season, PlayerGameLog.game_date,
                                 *(getattr(PlayerGameLog, c) for c in cols))
                          .where(PlayerGameLog.season_type == "regular", PlayerGameLog.season.in_(use)))
        logs = [dict(zip(("player", "season", "game_date", *cols), r)) for r in rows]
    return use, g_weights(logs)


@router.get("/options")
def options() -> dict:
    """Pickers for the UI: bases in the DB, models with descriptions, dollar methods, defaults."""
    with SessionLocal() as db:
        bases = []
        for kind, model in KINDS.items():
            for source, season, n in db.execute(
                select(model.source, model.season, func.count()).group_by(model.source, model.season)
                .order_by(model.season.desc(), model.source)
            ):
                bases.append({"kind": kind, "source": source, "season": season, "players": n})
    n_drafted, budget = _league_draft()
    return {
        "bases": bases,
        "basis": list(BASES),
        "models": [{"key": m.key, "label": m.label, "description": m.description, "needs": list(m.needs)}
                   for m in MODELS.values()],
        "dollars": [{"key": k, "description": d} for k, d in DOLLARS.items()],
        "categories": list(CATEGORIES),
        "pools": [144, 200, 250, None],
        "defaults": DEFAULTS,
        "drafted": n_drafted,
        "budget": budget,
    }


@router.get("")
def values(
    kind: str = DEFAULTS["kind"], source: str = DEFAULTS["source"], season: str = DEFAULTS["season"],
    basis: str = DEFAULTS["basis"], model: str = DEFAULTS["model"], punt: str = "",
    dollars: str = DEFAULTS["dollars"], pool: int = DEFAULTS["pool"], spread: float = DEFAULTS["spread"],
) -> dict:
    """Every player of the base with category z, total, rank and dollars. `pool=0` = all players.

    Stats are season totals (per game = total / gp). Market prices only for a season that has them.
    """
    if kind not in KINDS:
        raise HTTPException(400, f"kind must be one of {list(KINDS)}")
    if basis not in BASES or model not in MODELS or dollars not in DOLLARS:
        raise HTTPException(400, "unknown basis, model or dollars. See /api/valuation/options")
    punts = frozenset(c for c in punt.split(",") if c)
    if punts - set(CATEGORIES):
        raise HTTPException(400, f"unknown punt categories {sorted(punts - set(CATEGORIES))}")
    table = KINDS[kind]
    with SessionLocal() as db:
        base = {
            r.player_pk: r for r in db.scalars(select(table).where(table.source == source, table.season == season))
        }
        if not base:
            raise HTTPException(404, f"no {kind} rows for {source} {season}")
        players = {p.id: p for p in db.scalars(select(Player).where(Player.id.in_(base)))}
        # Market prices exist for the current season only; another season's base shows none.
        market: dict[int, dict] = {}
        for m in db.scalars(select(PlayerMarketValue).where(PlayerMarketValue.season == season,
                                                            PlayerMarketValue.player_pk.in_(base))):
            market.setdefault(m.player_pk, {})[m.source] = m
        # Positions and injury: always the current Yahoo feed (the league's own G, F, C set).
        yahoo_now = {m.player_pk: m for m in db.scalars(select(PlayerMarketValue).where(
            PlayerMarketValue.source == "yahoo", PlayerMarketValue.season == CURRENT_SEASON,
            PlayerMarketValue.player_pk.in_(base)))}
    g_from, gw = _g_weights(season) if model == "gscore" else ((), {})
    settings = Settings(basis=basis, pool=pool or None, punt=punts, g_weights=gw)
    n_drafted, budget = _league_draft()
    rows = {pk: {f: getattr(r, f) for f in STAT_FIELDS} for pk, r in base.items()}
    result = run(rows, model, settings, n_drafted=n_drafted, budget=budget, dollars=dollars, spread=spread)

    out = []
    for pk, r in base.items():
        p, v, mk = players[pk], result.get(pk), market.get(pk, {})
        y, e, yn = mk.get("yahoo"), mk.get("espn"), yahoo_now.get(pk)
        out.append({
            "player_id": pk,
            "name": f"{p.first_name} {p.last_name}",
            "team": p.team,
            "positions": (yn.positions if yn else None) or ([p.position] if p.position else None),
            "injury": yn.injury if yn else None,
            "stats": {f: getattr(r, f) for f in (*STAT_FIELDS, "min")},
            "z": v["z"] if v else None,
            "total": v["total"] if v else None,
            "rank": v["rank"] if v else None,
            "dollars": v["dollars"] if v else None,
            "market": {
                "yahoo_auction_value": y.auction_value if y else None,
                "yahoo_average_cost": y.average_cost if y else None,
                "espn_average_cost": e.average_cost if e else None,
            },
        })
    out.sort(key=lambda x: x["rank"] or 10**6)
    return {
        "settings": {"kind": kind, "source": source, "season": season, "basis": basis, "model": model,
                     "punt": sorted(punts), "dollars": dollars, "pool": pool or None, "spread": spread,
                     "drafted": n_drafted, "budget": budget,
                     "g_weights": gw or None, "g_weights_from": list(g_from) or None},
        "players": out,
    }
