"""Draft plan by build and the live draft assistant (T-030, VISION "Draft assistant"; user request 2026-10-17).

`GET /api/assistant/builds`: before the draft, the best 12 for 200 USD per build at room prices and how it
plays against dealt average rooms (`app/analytics/valuation/builds.py`). About 2 minutes; cached per base.
`POST /api/assistant/live`: during the draft, from the rosters so far (`assistant.py`). About a second.
"""

from functools import lru_cache

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.analytics.valuation import CATEGORIES
from app.analytics.valuation.assistant import Team, advise
from app.analytics.valuation.builds import BUILDS, dealt_opponents, knapsack, optimise, room_prices, team_eval
from app.analytics.valuation.simulate import expected_lines
from app.api.valuation import KINDS, _league_shape, _load, _run, _sim_inputs, market_prices
from app.seasons import CURRENT_SEASON
from app.sources.players.base import STAT_FIELDS

router = APIRouter(prefix="/api/assistant")

BLEND = 0.5  # room price = 0.5 market + 0.5 G-score dollars, rescaled (assumed, builds.py)


@lru_cache(maxsize=8)
def _prepared(kind: str, source: str, season: str, basis: str) -> dict:
    """Rows, expected weekly lines, G-score dollars, room prices and punt z-score dollars per build."""
    if kind not in KINDS:
        raise HTTPException(400, f"kind must be one of {list(KINDS)}")
    base, players, _, yahoo_now = _load(kind, source, season)
    res, _, _ = _run(base, "gscore", season, basis, frozenset(), "plain", 200, 10.0)
    rows = {pk: {f: getattr(r, f) or 0 for f in STAT_FIELDS} for pk, r in base.items()}
    pl, e = expected_lines(rows, basis, _sim_inputs(season))
    mk = market_prices() if season == CURRENT_SEASON else {}
    gdol = np.array([res[p]["dollars"] for p in pl])
    market = np.array([mk.get(p, 1.0) for p in pl]) if mk else gdol.copy()
    punt = {}
    for key, (_, punts) in BUILDS.items():
        if punts:
            pr, _, _ = _run(base, "punt", season, basis, frozenset(punts), "plain", 200, 10.0)
            punt[key] = np.array([pr[p]["dollars"] for p in pl])
    names = {pk: f"{p.first_name} {p.last_name}" for pk, p in players.items()}
    pos = {pk: (yahoo_now[pk].positions if pk in yahoo_now and yahoo_now[pk].positions else None)
           or ([p.position] if p.position else None) for pk, p in players.items()}
    return {"pos": pos, "pl": pl, "idx": {p: i for i, p in enumerate(pl)}, "e": e, "gdol": gdol, "market": market,
            "cost": room_prices(gdol, market, blend=BLEND), "punt": punt, "names": names,
            "ranked": np.array([i for i, _ in sorted(enumerate(pl), key=lambda t: res[t[1]]["rank"])])}


def _player(d: dict, i: int) -> dict:
    p = d["pl"][i]
    return {"player_id": p, "name": d["names"].get(p, str(p)), "positions": d["pos"].get(p), "room_price": int(d["cost"][i]),
            "market_price": round(float(d["market"][i]), 1), "gscore_dollars": round(float(d["gdol"][i]), 1)}


@lru_cache(maxsize=4)
def _builds(kind: str, source: str, season: str, basis: str) -> dict:
    d = _prepared(kind, source, season, basis)
    e, cost, ranked = d["e"], d["cost"], d["ranked"]
    _, slots, budget = _league_shape()
    cands = ranked[:220]
    out, rosters = [], {}
    order = [k for k in BUILDS if k != "none"] + ["none"]  # free last: it also starts from the best build
    for key in order:
        label, punts = BUILDS[key]
        vals = d["punt"].get(key, d["gdol"])
        starts = [[int(cands[j]) for j in knapsack(vals[cands], cost[cands], budget, slots)]]
        if key == "none":
            starts.append(rosters[max(out, key=lambda b: b["match_share"])["build"]])
        best = None
        for team in starts:
            for _ in range(2):  # the opponents depend on my roster: deal again after the first search
                opp = dealt_opponents(e, ranked, set(team), np.random.default_rng(5), 20)
                team = optimise(e, cands, cost, opp, punts, team, budget=budget)
            ev = team_eval(e, team, dealt_opponents(e, ranked, set(team), np.random.default_rng(99), 60), punts)
            if best is None or ev["match_share"] > best[1]["match_share"]:
                best = (team, ev)
        team, ev = best
        rosters[key] = team
        out.append({"build": key, "label": label, "punts": list(punts), **ev, "spent": int(cost[team].sum()),
                    "roster": [_player(d, i) for i in sorted(team, key=lambda i: -cost[i])]})
    out.sort(key=lambda b: -b["match_share"])
    return {"categories": list(CATEGORIES), "builds": out,
            "settings": {"kind": kind, "source": source, "season": season, "basis": basis, "blend": BLEND,
                         "rooms": 60, "budget": budget, "slots": slots}}


@router.get("/builds")
def builds(kind: str = "projection", source: str = "yahoo", season: str = CURRENT_SEASON, basis: str = "totals") -> dict:
    """Best roster per build at room prices and its shares against dealt average rooms."""
    return _builds(kind, source, season, basis)


class LiveTeam(BaseModel):
    team_id: int
    players: list[int]  # our player ids
    money_left: int
    open_slots: int
    mine: bool = False


class LiveRequest(BaseModel):
    kind: str = "projection"
    source: str = "yahoo"
    season: str = CURRENT_SEASON
    basis: str = "totals"
    teams: list[LiveTeam]
    nominated: int | None = None


@router.post("/live")
def live(body: LiveRequest) -> dict:
    """Assistant view for the draft so far: projection, builds, candidates, break-even price."""
    d = _prepared(body.kind, body.source, body.season, body.basis)
    idx = d["idx"]
    if sum(t.mine for t in body.teams) != 1:
        raise HTTPException(400, "exactly one team must be mine")
    teams = [Team(t.team_id, [idx[p] for p in t.players if p in idx], t.money_left, t.open_slots, t.mine)
             for t in body.teams]
    sold = {idx[p] for t in body.teams for p in t.players if p in idx}
    out = advise(d["e"], d["gdol"], d["cost"], d["punt"], teams, sold, idx.get(body.nominated))
    pl, names = d["pl"], d["names"]

    def person(i: int) -> dict:
        return {"player_id": pl[i], "name": names.get(pl[i], str(pl[i])), "positions": d["pos"].get(pl[i]),
                "live_price": out["price"].get(i)}

    return {
        "categories": out["categories"],
        "base": out["base"],
        "my_fill": [person(i) for i in out["my_fill"]],
        "builds": [{**b, "fill": [person(i) for i in b["fill"]]} for b in out["builds"]],
        "candidates": [{**person(c["row"]), **{k: v for k, v in c.items() if k != "row"}} for c in out["candidates"]],
        "breakeven": ({**person(out["breakeven"]["row"]), "price": out["breakeven"]["price"],
                       "live_price": out["breakeven"]["live_price"]} if out["breakeven"] else None),
        "money_left": out["money_left"], "open_slots": out["open_slots"],
        "unknown_players": [p for t in body.teams for p in t.players if p not in idx],
        "positions": {p: d["pos"].get(p) for t in body.teams if t.mine for p in t.players},
    }


def _punt_plan(plan: str, base: dict, season: str, basis: str) -> dict:
    """Sim room plan "build_<key>": my manager bids punt z-score dollars of that build."""
    punts = BUILDS[plan.removeprefix("build_")][1]
    res, _, _ = _run(base, "punt", season, basis, frozenset(punts), "plain", 200, 10.0)
    return {pk: r["dollars"] for pk, r in res.items()}


def register_sim_plans() -> None:
    from app.api import sim

    for key, (label, punts) in BUILDS.items():
        if punts:
            sim.register_plan(f"build_{key}", f"{label}: punt z-score dollars", _punt_plan)


register_sim_plans()
