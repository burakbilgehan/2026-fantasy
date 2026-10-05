"""Player values (T-010). Spec: docs/modules/valuation.md.

Values are computed on every request from the base rows (fast: under 0.1 s). Nothing is stored.
"""

from functools import lru_cache

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from app.analytics.valuation import BASES, CATEGORIES, MODELS, Settings, g_weights, run
from app.db import SessionLocal
from app.models import Draft, DraftPick, League, Player, PlayerAdvancedStats, PlayerExternalId, PlayerGameLog, PlayerMarketValue, PlayerProjection, PlayerSeasonStats
from app.seasons import CURRENT_SEASON, previous
from app.sources.players.base import STAT_FIELDS

router = APIRouter(prefix="/api/valuation")

KINDS = {"projection": PlayerProjection, "actual": PlayerSeasonStats}
DOLLARS = {
    "plain": "Value above replacement level. All drafted players share the league budget.",
    "savor": "Like plain, but cheap players are worth less because waivers replace them. Stars get more.",
}
# User decisions: default model Minus-1, pool 200 (2026-10-04); base Yahoo 2026-27 projection (2026-10-05).
DEFAULTS = {"kind": "projection", "source": "yahoo", "season": CURRENT_SEASON, "basis": "totals",
            "model": "minus1", "dollars": "plain", "pool": 200, "spread": 10.0}
NON_DRAFT_SLOTS = {"IL", "IL+", "NA"}
# Display names of the bases, in picker order (T-025 own projection first).
SOURCE_LABELS = {
    "own": "Own (LLM judged)", "own-base": "Own base (consensus)", "own-floor": "Own floor",
    "own-ceiling": "Own ceiling", "own-stat": "Own stat model", "yahoo": "Yahoo", "fanscout": "FanScout",
    "fantrax": "Fantrax", "espn": "ESPN", "nba": "NBA",
}


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
                label = SOURCE_LABELS.get(source, source.upper())
                kind_label = "projection" if kind == "projection" else "real stats"
                bases.append({"kind": kind, "source": source, "season": season, "players": n,
                              "label": f"{season} {label} {kind_label} ({n})"})
    # Our own projection first, then the outside projections, then real stats (newest season first).
    order = {s: i for i, s in enumerate(SOURCE_LABELS)}
    bases.sort(key=lambda b: (b["kind"] != "projection", -int(b["season"][:4]), order.get(b["source"], 99)))
    n_drafted, budget = _league_draft()
    curve, _, curve_from = room_prices()
    return {
        "bases": bases,
        # T-025 room price curve: price by rank in this room (index 0 = rank 1), docs/modules/pricing.md.
        "room_curve": [round(x, 1) for x in curve[:300]], "room_curve_from": curve_from,
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


def _check(kind: str, basis: str, dollars: str, punt: str, model: str | None = None) -> frozenset[str]:
    if kind not in KINDS:
        raise HTTPException(400, f"kind must be one of {list(KINDS)}")
    if basis not in BASES or dollars not in DOLLARS or (model is not None and model not in MODELS):
        raise HTTPException(400, "unknown basis, model or dollars. See /api/valuation/options")
    punts = frozenset(c for c in punt.split(",") if c)
    if punts - set(CATEGORIES):
        raise HTTPException(400, f"unknown punt categories {sorted(punts - set(CATEGORIES))}")
    return punts


def _load(kind: str, source: str, season: str) -> tuple[dict, dict, dict, dict]:
    """(base rows, players, market per source, current Yahoo row), each keyed by player id."""
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
    return base, players, market, yahoo_now


def room_prices() -> tuple[list[float], dict[int, float], str]:
    """(room price curve by rank, expected room price per player, where the curve comes from).
    Curve: our league's last real auction (the room's own shape). Expected price: the market order
    (Yahoo, ESPN average cost, Fantrax ADP) mapped onto that curve. docs/modules/pricing.md."""
    from app.analytics.valuation import room

    with SessionLocal() as db:
        d = db.scalar(select(Draft).where(Draft.kind == "past_league").order_by(Draft.season.desc()))
        prices = [p for (p,) in db.execute(select(DraftPick.price).where(DraftPick.draft_pk == d.id))] if d else []
        signals: dict[str, dict[int, float]] = {"yahoo": {}, "espn": {}, "fantrax": {}}
        for m in db.scalars(select(PlayerMarketValue).where(PlayerMarketValue.season == CURRENT_SEASON,
                                                            PlayerMarketValue.source.in_(list(signals)))):
            v = m.average_pick if m.source == "fantrax" else m.average_cost
            if v:
                signals[m.source][m.player_pk] = v
    ranks = room.market_ranks(signals)
    curve = room.price_curve(prices or [1.0], max(len(ranks), 600))
    return curve, room.expected_prices(ranks, curve), f"{d.season} league auction" if d else "none"


def usage_season(kind: str, season: str) -> str:
    """Season of the usage rate shown next to a base: its own season for real stats, the season
    before for projections (no projection source gives usage)."""
    return season if kind == "actual" else previous(season)


def nba_ids(pks) -> dict[int, str]:
    """NBA person id per player (headshot URL in the frontend)."""
    with SessionLocal() as db:
        return dict(db.execute(select(PlayerExternalId.player_pk, PlayerExternalId.external_id).where(
            PlayerExternalId.source == "nba", PlayerExternalId.player_pk.in_(list(pks)))).all())


def _usage(pks, season: str) -> dict[int, float]:
    with SessionLocal() as db:
        return dict(db.execute(select(PlayerAdvancedStats.player_pk, PlayerAdvancedStats.usg_pct).where(
            PlayerAdvancedStats.source == "nba", PlayerAdvancedStats.season == season,
            PlayerAdvancedStats.player_pk.in_(list(pks)))).all())


def _run(base: dict, model: str, season: str, basis: str, punts: frozenset[str], dollars: str, pool: int,
         spread: float) -> tuple[dict, tuple[str, ...], dict]:
    """Values of the whole base pool with one model: (result per player, g-score seasons, g-score weights)."""
    g_from, gw = _g_weights(season) if model == "gscore" else ((), {})
    settings = Settings(basis=basis, pool=pool or None, punt=punts, g_weights=gw)
    n_drafted, budget = _league_draft()
    rows = {pk: {f: getattr(r, f) for f in STAT_FIELDS} for pk, r in base.items()}
    return run(rows, model, settings, n_drafted=n_drafted, budget=budget, dollars=dollars, spread=spread), g_from, gw


def off_categories(model: str, z: dict[str, float], punts: frozenset[str]) -> list[str]:
    """Categories the model does not count for this player (punted, or the player's dropped worst one)."""
    if model == "punt":
        return [c for c in CATEGORIES if c in punts]
    if model in ("minus1", "durant"):
        pool = [c for c in CATEGORIES if model == "minus1" or c != "tov"]
        worst = min(pool, key=lambda c: z[c])
        return [worst] if model == "minus1" else sorted({"tov", worst}, key=CATEGORIES.index)
    return []


@router.get("")
def values(
    kind: str = DEFAULTS["kind"], source: str = DEFAULTS["source"], season: str = DEFAULTS["season"],
    basis: str = DEFAULTS["basis"], model: str = DEFAULTS["model"], punt: str = "",
    dollars: str = DEFAULTS["dollars"], pool: int = DEFAULTS["pool"], spread: float = DEFAULTS["spread"],
) -> dict:
    """Every player of the base with category z, total, rank and dollars. `pool=0` = all players.

    Stats are season totals (per game = total / gp). Market prices only for a season that has them.
    """
    punts = _check(kind, basis, dollars, punt, model)
    base, players, market, yahoo_now = _load(kind, source, season)
    result, g_from, gw = _run(base, model, season, basis, punts, dollars, pool, spread)
    n_drafted, budget = _league_draft()
    usg_season = usage_season(kind, season)
    usage = _usage(base, usg_season)
    nba = nba_ids(base)
    _, expected, _ = room_prices()

    out = []
    for pk, r in base.items():
        p, v, mk = players[pk], result.get(pk), market.get(pk, {})
        y, e, fx, yn = mk.get("yahoo"), mk.get("espn"), mk.get("fantrax"), yahoo_now.get(pk)
        out.append({
            "player_id": pk,
            "nba_id": nba.get(pk),
            "name": f"{p.first_name} {p.last_name}",
            "team": p.team,
            "positions": (yn.positions if yn else None) or ([p.position] if p.position else None),
            "injury": yn.injury if yn else None,
            "stats": {f: getattr(r, f) for f in (*STAT_FIELDS, "min")},
            "usg_pct": usage.get(pk),
            "z": v["z"] if v else None,
            "total": v["total"] if v else None,
            "rank": v["rank"] if v else None,
            "dollars": v["dollars"] if v else None,
            "market": {
                "yahoo_auction_value": y.auction_value if y else None,
                "yahoo_average_cost": y.average_cost if y else None,
                "espn_average_cost": e.average_cost if e else None,
                "fantrax_adp": fx.average_pick if fx else None,
                # T-025: what this room is expected to pay (market order on the room's price curve).
                # The frontend adds "room value" = curve at our model rank, and opportunity = the gap.
                "room_expected": round(expected.get(pk, 1.0), 1) if season == CURRENT_SEASON else None,
            },
        })
    out.sort(key=lambda x: x["rank"] or 10**6)
    return {
        "settings": {"kind": kind, "source": source, "season": season, "basis": basis, "model": model,
                     "punt": sorted(punts), "dollars": dollars, "pool": pool or None, "spread": spread,
                     "drafted": n_drafted, "budget": budget,
                     "g_weights": gw or None, "g_weights_from": list(g_from) or None,
                     "usage_season": usg_season},
        "players": out,
    }


@router.get("/player/{player_pk}")
def player_models(
    player_pk: int, kind: str = DEFAULTS["kind"], source: str = DEFAULTS["source"],
    season: str = DEFAULTS["season"], basis: str = DEFAULTS["basis"], punt: str = "",
    dollars: str = DEFAULTS["dollars"], pool: int = DEFAULTS["pool"], spread: float = DEFAULTS["spread"],
) -> dict:
    """One player's z, total, rank and dollars in every model. Each model runs on the whole base pool,
    because rank and dollars are relative to the pool. `off` = categories the model does not count.
    The punt model with no punted category is the same as Z-score 9-cat."""
    punts = _check(kind, basis, dollars, punt)
    base, _, _, _ = _load(kind, source, season)
    if player_pk not in base:
        return {"in_base": False, "models": []}
    out = []
    for key, m in MODELS.items():
        result, _, _ = _run(base, key, season, basis, punts, dollars, pool, spread)
        v = result.get(player_pk)
        out.append({"key": key, "label": m.label,
                    "z": v["z"] if v else None, "total": v["total"] if v else None,
                    "rank": v["rank"] if v else None, "dollars": v["dollars"] if v else None,
                    "off": off_categories(key, v["z"], punts) if v else []})
    # Season totals of the base row; the drawer shows per game values next to the z (per game = total / gp).
    stats = {f: getattr(base[player_pk], f) for f in STAT_FIELDS}
    return {"in_base": True, "stats": stats, "models": out}
