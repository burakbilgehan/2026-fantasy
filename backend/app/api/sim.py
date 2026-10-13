"""Room simulation for the Sim page (docs/modules/draft.md, T-030 seed): 12 managers with different
valuations run an auction, then play a Monte Carlo season. `app/analytics/draftsim.py` does the work.

Room: 4 managers who pay the market price (Yahoo x2, ESPN, Fantrax), 2 on z-score dollars, 1 Minus-1,
1 DURANT H2H, 1 on points-league dollars, 1 "stars first" (G-score, pays 25% more for the top 15),
1 "bargain hunter" (G-score, never above 80% of the market for the top 30, pays 25% more under 15 USD),
plus me on G-score dollars with the chosen plan. Bases without market prices (past seasons) use G-score
dollars as the market.
"""

from functools import lru_cache

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.analytics.draftsim import Manager, auction, play
from app.analytics.valuation import CATEGORIES, to_dollars
from app.api.valuation import KINDS, _league_draft, _load, _run, _sim_inputs, market_prices
from app.seasons import CURRENT_SEASON
from app.sources.players.base import STAT_FIELDS

router = APIRouter(prefix="/api/sim")

PLANS = {
    "balanced": "Balanced: G-score dollars, no plan",
    "one_star": "One star: pay up to 110% of the market for one of the top 3, the rest at G-score dollars",
    "two_stars": "Two stars: the same for two of the top 3",
    "bargains_plus": "Bargains +30%: pay 30% over G-score dollars for players the model values 1.5x the market, stars at value",
    "no_stars": "No stars: skip the top 10 by market price, bargains +30%",
}
ROOM = [("Market A", "market"), ("Market B", "market"), ("Market C", "market"), ("Market D", "market"),
        ("Z-score", "zscore"), ("Z-score 2", "zscore"), ("Minus-1", "minus1"), ("DURANT", "durant"),
        ("Points league", "points"), ("Stars first", "stars"), ("Bargain hunter", "bargain")]


class RoomRequest(BaseModel):
    kind: str = "projection"
    source: str = "yahoo"
    season: str = CURRENT_SEASON
    basis: str = "totals"
    plan: str = "one_star"
    seed: int = 1
    seasons: int = 300


def _dollars(base: dict, model: str, season: str, basis: str) -> dict:
    res, _, _ = _run(base, model, season, basis, frozenset(), "plain", 200, 10.0)
    return {pk: r["dollars"] for pk, r in res.items()}


def _points_dollars(base: dict, n: int, budget: float) -> dict:
    pts = {pk: (r.pts or 0) + 1.2 * (r.reb or 0) + 1.5 * (r.ast or 0) + 3 * (r.stl or 0) + 3 * (r.blk or 0) - (r.tov or 0)
           for pk, r in base.items() if r.gp}
    return to_dollars(pts, n, budget, "plain")


def _plan_values(plan: str, g: dict, market: dict) -> tuple[dict, set, int, float]:
    """(values, star set, max stars, star factor) for my manager."""
    top3 = set(sorted(g, key=g.get, reverse=True)[:3])
    top10_market = set(sorted(market, key=market.get, reverse=True)[:10])
    if plan == "balanced":
        return dict(g), set(), 0, 1.0
    if plan in ("one_star", "two_stars"):
        vals = dict(g)
        for p in top3:
            vals[p] = max(g[p], 1.1 * market.get(p, g[p]))
        return vals, top3, 1 if plan == "one_star" else 2, 1.0
    if plan == "bargains_plus":
        return {p: v * 1.3 if (market.get(p, 1) >= 1 and v >= 1.5 * market.get(p, 1) and v >= 5) else v for p, v in g.items()}, set(), 0, 1.0
    if plan == "no_stars":
        return {p: 0.0 if p in top10_market else (v * 1.3 if v >= 1.5 * market.get(p, 1) and v >= 5 else v) for p, v in g.items()}, set(), 0, 1.0
    raise HTTPException(400, f"plan must be one of {list(PLANS)}")


def _managers(plan: str, g: dict, z: dict, m1: dict, du: dict, pts: dict, market: dict) -> list[Manager]:
    top15 = set(sorted(g, key=g.get, reverse=True)[:15])
    top30_market = set(sorted(market, key=market.get, reverse=True)[:30])
    out = []
    for name, style in ROOM:
        if style == "market":
            vals = {p: float(v) for p, v in market.items()}
        elif style == "zscore":
            vals = dict(z)
        elif style == "minus1":
            vals = dict(m1)
        elif style == "durant":
            vals = dict(du)
        elif style == "points":
            vals = dict(pts)
        elif style == "stars":
            vals = {p: v * (1.25 if p in top15 else 0.9) for p, v in g.items()}
        else:  # bargain
            vals = {p: min(v, 0.8 * market.get(p, v)) if p in top30_market else (v * 1.25 if market.get(p, 1) <= 15 else v)
                    for p, v in g.items()}
        out.append(Manager(name, style, vals, noise=0.15 if style == "market" else 0.12))
    vals, stars, max_stars, factor = _plan_values(plan, g, market)
    me = Manager("Me", plan, vals, mine=True, noise=0.05, stars=stars, max_stars=max_stars, plain_values=dict(g))
    return out + [me]


@lru_cache(maxsize=16)
def _room(kind: str, source: str, season: str, basis: str, plan: str, seed: int, seasons: int) -> dict:
    base, players, _, _ = _load(kind, source, season)
    n_drafted, budget = _league_draft()
    teams_n = len(ROOM) + 1
    slots = n_drafted // 12
    g = _dollars(base, "gscore", season, basis)
    z = _dollars(base, "zscore", season, basis)
    m1 = _dollars(base, "minus1", season, basis)
    du = _dollars(base, "durant", season, basis)
    pts = _points_dollars(base, n_drafted, budget)
    market = {p: v for p, v in market_prices().items() if p in base} if season == CURRENT_SEASON else {}
    if not market:
        market = dict(g)
    managers = _managers(plan, g, z, m1, du, pts, market)
    for m in managers:
        m.money, m.slots = int(budget / 12), slots
    rng = np.random.default_rng(seed)
    order = sorted(market, key=market.get, reverse=True)
    log = auction(managers, order, rng)
    rows = {pk: {f: getattr(r, f) or 0 for f in STAT_FIELDS} for pk, r in base.items()}
    result = play([m.roster for m in managers], rows, basis, _sim_inputs(season), rng, seasons=seasons)
    names = {pk: f"{p.first_name} {p.last_name}" for pk, p in players.items()}
    teams = []
    for i, m in enumerate(managers):
        spent = sum(m.paid.values())
        teams.append({
            "team": i, "name": m.name, "style": m.style, "mine": m.mine, "spent": spent, "left": m.money,
            "roster": [{"player_id": p, "name": names.get(p, str(p)), "price": m.paid[p],
                        "gscore_dollars": round(g.get(p, 0.0), 1), "market_price": round(market.get(p, 1.0), 1)}
                       for p in sorted(m.roster, key=lambda q: -m.paid[q])],
            "cat_share": round(result["cat_share"][i], 1), "wins": round(result["wins"][i], 1),
            "losses": round(result["games"] - result["wins"][i], 1),
            "playoffs": round(result["playoffs"][i], 1), "titles": round(result["titles"][i], 1),
            "per_cat": [round(x, 1) for x in result["per_cat"][i]],
        })
    teams.sort(key=lambda t: (-t["wins"], -t["cat_share"]))
    return {
        "settings": {"kind": kind, "source": source, "season": season, "basis": basis, "plan": plan, "seed": seed,
                     "seasons": seasons, "weeks": result["weeks"], "games": result["games"], "teams": teams_n,
                     "market_is_model": season != CURRENT_SEASON},
        "categories": list(CATEGORIES),
        "teams": teams,
        "log": [{**r, "player_id": r["player"], "name": names.get(r["player"], str(r["player"]))} for r in log],
    }


@router.get("/plans")
def plans() -> dict:
    return {"plans": [{"key": k, "label": v} for k, v in PLANS.items()],
            "room": [{"name": n, "style": s} for n, s in ROOM]}


@router.post("/room")
def room(body: RoomRequest) -> dict:
    """One simulated auction and season. Deterministic for a seed; cached."""
    if body.kind not in KINDS:
        raise HTTPException(400, f"kind must be one of {list(KINDS)}")
    if body.plan not in PLANS:
        raise HTTPException(400, f"plan must be one of {list(PLANS)}")
    out = _room(body.kind, body.source, body.season, body.basis, body.plan, body.seed, max(20, min(body.seasons, 1000)))
    for r in out["log"]:
        r.pop("player", None)
    return out
