"""Room simulation for the Sim page (docs/modules/draft.md, T-030 seed): 12 managers with different
valuations run an auction, then play a Monte Carlo season. `app/analytics/draftsim.py` does the work.

Two rooms (`room` field). Bases without market prices (past seasons) use G-score dollars as the market.

"strong" (default, 2026-10-17): a fair test bed. Beating weak drafters proves nothing (user), so every
opponent drafts well:
- Model: 5 on G-score, 3 on z-score, 3 on DURANT H2H dollars (the strong models of the backtest,
  docs/modules/valuation-models-research.md). No points-league, bargain-only or market-only manager.
- Market anchor: value = 0.5 x model dollars + 0.5 x market price (1 USD when the market has no price), so
  bids stay near what the room pays. Market dollars sum to less than the budget (few players above 1 USD), so
  each opponent then rescales his values above 1 USD (v' = 1 + k(v - 1)) until his own top `n_drafted`
  values sum to the room budget: a good drafter plans to spend all his money.
- Budget shape (spread over the room: 4 balanced, 4 one star, 3 two stars), a real plan, three parts:
  1. Reserve: every bid is capped at money left - (open slots - 1) x reserve (`draftsim.bid_cap`), reserve =
     a share of the budget per slot (SHAPES). He never spends himself out of the tier he plans to fill with.
     When the plan is broken (money per slot below the reserve), the reserve drops to an even split.
  2. Stars: "one star" and "two stars" value the top STAR_POOL players (by their own values) at STAR_FACTOR x,
     until they have won 1 or 2 of them; after that those players go back to plain value.
  3. Spend-down (`draftsim.spend_factor`): when his money is more than his own values of the best players
     left for his open slots, he raises his bids by that ratio (at most 3x). Money left at the end is wasted.
  Measured (2026-27 Yahoo projection base, seeds 1-10): every opponent ends with 0-5 USD left on average;
  room prices match the market from rank 6 to 50, the top 5 sell about 15% above it (star chasers bid
  against each other). Balanced shapes win most (about 12.5 of 20), two-star shapes least (about 6.5).
- Bid noise: lognormal sigma 0.12 for everyone, me included, so a result measures the plan, not an
  information edge. Auction and season use separate random streams (seed, 1) and (seed, 2), so the
  opponents' season luck does not depend on how many bids my plan made.

"legacy" (the first Sim room, 2026-10-13, kept so old results reproduce): 4 managers who pay the market
price (Yahoo x2, ESPN, Fantrax; noise 0.15), 2 on z-score dollars, 1 Minus-1, 1 DURANT H2H, 1 on
points-league dollars, 1 "stars first" (G-score, pays 25% more for the top 15), 1 "bargain hunter" (G-score,
never above 80% of the market for the top 30, pays 25% more under 15 USD); reserve 1 USD; me with noise 0.05;
one random stream for auction and season.

My manager: G-score dollars with the chosen plan (PLANS), reserve 1 USD and no spend-down in both rooms
(the plans stay as defined). Extension point:
`PLAN_PROVIDERS[key](plan, base, season, basis) -> {player: dollars} | None`, registered with
`register_plan`; `_plan_values` asks it first. `/compare` runs every plan over seeds 1..N and returns
means with standard errors: one seed is noise.
"""

import time
from functools import lru_cache
from typing import Callable

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
# Extra plans for my manager: key -> fn(plan, base, season, basis) returning dollars per player (or None).
PLAN_PROVIDERS: dict[str, Callable[[str, dict, str, str], dict | None]] = {}

LEGACY_ROOM = [("Market A", "market"), ("Market B", "market"), ("Market C", "market"), ("Market D", "market"),
               ("Z-score", "zscore"), ("Z-score 2", "zscore"), ("Minus-1", "minus1"), ("DURANT", "durant"),
               ("Points league", "points"), ("Stars first", "stars"), ("Bargain hunter", "bargain")]
ROOM = LEGACY_ROOM  # old name
# (name, model, budget shape)
STRONG_ROOM = [("G-score A", "gscore", "balanced"), ("G-score B", "gscore", "one_star"),
               ("G-score C", "gscore", "two_stars"), ("G-score D", "gscore", "balanced"),
               ("G-score E", "gscore", "one_star"), ("Z-score A", "zscore", "two_stars"),
               ("Z-score B", "zscore", "balanced"), ("Z-score C", "zscore", "one_star"),
               ("DURANT A", "durant", "two_stars"), ("DURANT B", "durant", "balanced"),
               ("DURANT C", "durant", "one_star")]
ROOMS = ("strong", "legacy")
ROOM_RULES = {
    "strong": "Strong room: 11 opponents on G-score (5), z-score (3) and DURANT (3) dollars, each half model and "
              "half market price, scaled to spend the whole budget. Budget shapes: 4 balanced, 4 one star, 3 two "
              "stars, each with a money reserve per open slot. Everyone, me included, bids with the same noise.",
    "legacy": "Legacy room: 4 managers pay the market price, 2 use z-score, 1 Minus-1, 1 DURANT, 1 points-league "
              "dollars, 1 chases stars, 1 hunts bargains, and me (with less bid noise than the others).",
}
ANCHOR = 0.5  # weight of the model dollars in a strong opponent's value; the rest is the market price
NOISE = 0.12  # lognormal bid sigma in the strong room, me included
# Budget shape: (reserve as a share of the budget per slot, stars wanted). Balanced: the reserve caps his
# first bid at 90 USD and keeps him buying in the 30-50 tier; two stars: low reserve, two top players.
SHAPES = {"balanced": (0.6, 0), "one_star": (0.4, 1), "two_stars": (0.25, 2)}
STAR_POOL = 10  # the "stars" of a star shape: his own top 10
STAR_FACTOR = 1.1


class RoomRequest(BaseModel):
    kind: str = "projection"
    source: str = "yahoo"
    season: str = CURRENT_SEASON
    basis: str = "totals"
    plan: str = "one_star"
    seed: int = 1
    seasons: int = 300
    room: str = "strong"


class CompareRequest(BaseModel):
    kind: str = "projection"
    source: str = "yahoo"
    season: str = CURRENT_SEASON
    basis: str = "totals"
    room: str = "strong"
    plans: list[str] = []  # empty: every plan
    seeds: int = 20
    seasons: int = 100


def register_plan(key: str, label: str, fn: Callable[[str, dict, str, str], dict | None]) -> None:
    """Adds a plan for my manager (for example a punt build). `fn` returns dollars per player."""
    PLANS[key] = label
    PLAN_PROVIDERS[key] = fn


def plan_values_hook(plan: str, base: dict, season: str, basis: str) -> dict | None:
    """Dollars per player from a registered provider; None for the built-in plans."""
    fn = PLAN_PROVIDERS.get(plan)
    return fn(plan, base, season, basis) if fn else None


def _dollars(base: dict, model: str, season: str, basis: str) -> dict:
    res, _, _ = _run(base, model, season, basis, frozenset(), "plain", 200, 10.0)
    return {pk: r["dollars"] for pk, r in res.items()}


def _points_dollars(base: dict, n: int, budget: float) -> dict:
    pts = {pk: (r.pts or 0) + 1.2 * (r.reb or 0) + 1.5 * (r.ast or 0) + 3 * (r.stl or 0) + 3 * (r.blk or 0) - (r.tov or 0)
           for pk, r in base.items() if r.gp}
    return to_dollars(pts, n, budget, "plain")


def _plan_values(plan: str, g: dict, market: dict, base: dict | None = None, season: str = CURRENT_SEASON,
                 basis: str = "totals") -> tuple[dict, set, int, float]:
    """(values, star set, max stars, star factor) for my manager."""
    hooked = plan_values_hook(plan, base or {}, season, basis)
    if hooked is not None:
        return {p: float(v) for p, v in hooked.items()}, set(), 0, 1.0
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


def anchored_values(model: dict, market: dict, n_drafted: int, budget: float) -> dict:
    """A strong opponent's dollars: ANCHOR x model + (1 - ANCHOR) x market (1 USD when the market has no
    price), then the part above 1 USD scaled so that his top `n_drafted` values sum to `budget`."""
    blend = {p: ANCHOR * v + (1 - ANCHOR) * market.get(p, 1.0) for p, v in model.items()}
    top = sorted(blend.values(), reverse=True)[:n_drafted]
    surplus = sum(v - 1.0 for v in top if v > 1.0)
    fixed = sum(1.0 if v > 1.0 else v for v in top)
    k = (budget - fixed) / surplus if surplus > 0 else 1.0
    return {p: 1.0 + k * (v - 1.0) if v > 1.0 else v for p, v in blend.items()}


def _strong_manager(name: str, model: str, shape: str, dollars: dict, market: dict, n_drafted: int, budget: float,
                    per_slot: float) -> Manager:
    plain = anchored_values(dollars, market, n_drafted, budget)
    share, stars_wanted = SHAPES[shape]
    vals, stars = dict(plain), set()
    if stars_wanted:
        stars = set(sorted(plain, key=plain.get, reverse=True)[:STAR_POOL])
        for p in stars:
            vals[p] = plain[p] * STAR_FACTOR
    return Manager(name, f"{model} {shape}", vals, noise=NOISE, stars=stars, max_stars=stars_wanted,
                   plain_values=plain, reserve=share * per_slot, spend_down=True)


def _managers(room: str, plan: str, inp: dict) -> list[Manager]:
    """The 11 opponents of the room plus me. `inp`: the cached inputs of `_inputs` (or the same keys)."""
    g, market = inp["g"], inp["market"]
    out = []
    if room == "strong":
        per_slot = inp["budget"] / inp["teams"] / inp["slots"]
        for name, model, shape in STRONG_ROOM:
            out.append(_strong_manager(name, model, shape, inp[model], market, inp["n_drafted"], inp["budget"], per_slot))
    else:
        top15 = set(sorted(g, key=g.get, reverse=True)[:15])
        top30_market = set(sorted(market, key=market.get, reverse=True)[:30])
        for name, style in LEGACY_ROOM:
            if style == "market":
                vals = {p: float(v) for p, v in market.items()}
            elif style in ("zscore", "minus1", "durant", "points"):
                vals = dict(inp[style])
            elif style == "stars":
                vals = {p: v * (1.25 if p in top15 else 0.9) for p, v in g.items()}
            else:  # bargain
                vals = {p: min(v, 0.8 * market.get(p, v)) if p in top30_market else (v * 1.25 if market.get(p, 1) <= 15 else v)
                        for p, v in g.items()}
            out.append(Manager(name, style, vals, noise=0.15 if style == "market" else 0.12))
    vals, stars, max_stars, _ = _plan_values(plan, g, market, inp.get("base"), inp.get("season", CURRENT_SEASON),
                                             inp.get("basis", "totals"))
    me = Manager("Me", plan, vals, mine=True, noise=NOISE if room == "strong" else 0.05, stars=stars,
                 max_stars=max_stars, plain_values=dict(g))
    return out + [me]


@lru_cache(maxsize=8)
def _inputs(kind: str, source: str, season: str, basis: str) -> dict:
    """Everything a room needs that does not depend on the plan or the seed. Callers must not mutate it."""
    base, players, _, _ = _load(kind, source, season)
    n_drafted, budget = _league_draft()
    g = _dollars(base, "gscore", season, basis)
    market = {p: v for p, v in market_prices().items() if p in base} if season == CURRENT_SEASON else {}
    market_is_model = not market
    if not market:
        market = dict(g)
    return {
        "base": base, "season": season, "basis": basis, "n_drafted": n_drafted, "budget": budget, "teams": 12,
        "slots": n_drafted // 12, "g": g, "gscore": g, "zscore": _dollars(base, "zscore", season, basis),
        "minus1": _dollars(base, "minus1", season, basis), "durant": _dollars(base, "durant", season, basis),
        "points": _points_dollars(base, n_drafted, budget), "market": market, "market_is_model": market_is_model,
        "rows": {pk: {f: getattr(r, f) or 0 for f in STAT_FIELDS} for pk, r in base.items()},
        "names": {pk: f"{p.first_name} {p.last_name}" for pk, p in players.items()},
    }


def _simulate(inp: dict, room: str, plan: str, seed: int, seasons: int) -> tuple[list[Manager], list[dict], dict]:
    """One auction and one Monte Carlo season block: (managers after the draft, auction log, season result)."""
    managers = _managers(room, plan, inp)
    for m in managers:
        m.money, m.slots = int(inp["budget"] / inp["teams"]), inp["slots"]
    if room == "legacy":
        rng_auction = rng_season = np.random.default_rng(seed)
    else:
        rng_auction, rng_season = np.random.default_rng([seed, 1]), np.random.default_rng([seed, 2])
    market = inp["market"]
    order = sorted(market, key=market.get, reverse=True)
    log = auction(managers, order, rng_auction)
    result = play([m.roster for m in managers], inp["rows"], inp["basis"], _sim_inputs(inp["season"]), rng_season,
                  seasons=seasons)
    return managers, log, result


def _check(kind: str, room: str, plans: list[str]) -> None:
    if kind not in KINDS:
        raise HTTPException(400, f"kind must be one of {list(KINDS)}")
    if room not in ROOMS:
        raise HTTPException(400, f"room must be one of {list(ROOMS)}")
    bad = [p for p in plans if p not in PLANS and p not in PLAN_PROVIDERS]
    if bad:
        raise HTTPException(400, f"plan must be one of {list(PLANS)}; got {bad}")


@lru_cache(maxsize=16)
def _room(kind: str, source: str, season: str, basis: str, plan: str, seed: int, seasons: int,
          room: str = "strong") -> dict:
    inp = _inputs(kind, source, season, basis)
    g, market, names = inp["g"], inp["market"], inp["names"]
    managers, log, result = _simulate(inp, room, plan, seed, seasons)
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
                     "seasons": seasons, "weeks": result["weeks"], "games": result["games"], "teams": len(managers),
                     "market_is_model": inp["market_is_model"], "room": room, "room_rule": ROOM_RULES[room]},
        "categories": list(CATEGORIES),
        "teams": teams,
        "log": [{**r, "player_id": r["player"], "name": names.get(r["player"], str(r["player"]))} for r in log],
    }


def _mean_se(xs: list[float]) -> tuple[float, float]:
    a = np.asarray(xs, dtype=float)
    se = float(a.std(ddof=1) / np.sqrt(len(a))) if len(a) > 1 else 0.0
    return round(float(a.mean()), 2), round(se, 2)


def compare_plans(kind: str, source: str, season: str, basis: str, room: str, plans: list[str], seeds: int,
                  seasons: int) -> dict:
    """Every plan over seeds 1..`seeds`: mean and standard error (over seeds) of my wins, category share,
    playoff and title odds, and money spent. Also the opponents' mean wins, to check that the room is even."""
    t0 = time.perf_counter()
    inp = _inputs(kind, source, season, basis)
    rows, opp = [], {}
    games = 0
    for plan in plans:
        acc = {k: [] for k in ("wins", "cat_share", "playoffs", "titles", "spent")}
        for seed in range(1, seeds + 1):
            managers, _, result = _simulate(inp, room, plan, seed, seasons)
            games = result["games"]
            for i, m in enumerate(managers):
                if m.mine:
                    acc["wins"].append(result["wins"][i])
                    acc["cat_share"].append(result["cat_share"][i])
                    acc["playoffs"].append(result["playoffs"][i])
                    acc["titles"].append(result["titles"][i])
                    acc["spent"].append(sum(m.paid.values()))
                else:
                    o = opp.setdefault(m.name, {"name": m.name, "style": m.style, "wins": [], "spent": []})
                    o["wins"].append(result["wins"][i])
                    o["spent"].append(sum(m.paid.values()))
        row = {"plan": plan, "label": PLANS.get(plan, plan)}
        for k, xs in acc.items():
            row[k], row[f"{k}_se"] = _mean_se(xs)
        rows.append(row)
    opponents = [{"name": o["name"], "style": o["style"], "wins": _mean_se(o["wins"])[0],
                  "spent": _mean_se(o["spent"])[0]} for o in opp.values()]
    return {
        "settings": {"kind": kind, "source": source, "season": season, "basis": basis, "room": room, "seeds": seeds,
                     "seasons": seasons, "games": games, "teams": len(STRONG_ROOM if room == "strong" else LEGACY_ROOM) + 1,
                     "market_is_model": inp["market_is_model"], "room_rule": ROOM_RULES[room],
                     "elapsed_s": round(time.perf_counter() - t0, 1)},
        "plans": rows,
        "opponents": sorted(opponents, key=lambda o: -o["wins"]),
    }


@router.get("/plans")
def plans() -> dict:
    return {"plans": [{"key": k, "label": v} for k, v in PLANS.items()],
            "room": [{"name": n, "style": f"{m} {s}"} for n, m, s in STRONG_ROOM],
            "rooms": {"strong": {"rule": ROOM_RULES["strong"],
                                 "managers": [{"name": n, "style": f"{m} {s}"} for n, m, s in STRONG_ROOM]},
                      "legacy": {"rule": ROOM_RULES["legacy"],
                                 "managers": [{"name": n, "style": s} for n, s in LEGACY_ROOM]}}}


@router.post("/room")
def room(body: RoomRequest) -> dict:
    """One simulated auction and season. Deterministic for a seed; cached."""
    _check(body.kind, body.room, [body.plan])
    out = _room(body.kind, body.source, body.season, body.basis, body.plan, body.seed,
                max(20, min(body.seasons, 1000)), body.room)
    for r in out["log"]:
        r.pop("player", None)
    return out


@router.post("/compare")
def compare(body: CompareRequest) -> dict:
    """Every plan over seeds 1..N in the same room. Means with standard errors over seeds."""
    plans_ = body.plans or list(PLANS)
    _check(body.kind, body.room, plans_)
    return compare_plans(body.kind, body.source, body.season, body.basis, body.room, plans_,
                         max(2, min(body.seeds, 200)), max(20, min(body.seasons, 1000)))
