"""Draft assistant (VISION "Draft assistant", user request 2026-10-17): live guidance from the rosters so far.

A simplified team-conditional value, not H-score (T-027 comes after the draft). Steps, on every call:
1. Live room price: the room price of `builds.room_prices`, rescaled so the best players left (as many as
   the open slots of all teams) cost the money all teams have left (inflation follows the room).
2. Projection: every team fills its open slots with the best G-score dollars it can buy at live room prices
   (a knapsack), richest team first, from the players left. My team the same: the "plain" plan.
3. Standing: my projected team against the 11 projected teams, with weekly noise (`builds.win_probs`):
   matchup probability, category probabilities, my rank in every category.
4. Builds: for every build of `builds.BUILDS` (free, forced punts), the best fill of my open slots
   (`builds.optimise` from a punt z-score knapsack). Shows which direction the players I hold point to.
5. Candidates: each of the best players left joins my team at his live room price, the rest of the slots
   are refilled with the money left; compared with my best fill without him, the change in matchup and
   category probabilities is his worth to my team, money cost included. The nominated player also gets a
   break-even price: the highest price at which buying him still beats the best fill without him.
Pure numpy, no DB.
"""

from dataclasses import dataclass

import numpy as np

from app.analytics.valuation.builds import BUILDS, _scores, cat_moments, knapsack, optimise
from app.analytics.valuation.core import CATEGORIES

FILL_POOL = 150  # players left considered for fills, best G-score dollars first
CANDIDATES = 40


@dataclass
class Team:
    team_id: int
    players: list[int]  # row indices
    money: int
    slots: int  # open slots
    mine: bool = False


def live_prices(base_cost: np.ndarray, avail: np.ndarray, money: int, slots: int) -> np.ndarray:
    """Room prices rescaled to the money left: the best `slots` players left cost `money` together."""
    price = base_cost.astype(float).copy()
    if slots <= 0 or not len(avail):
        return np.maximum(1, np.rint(price)).astype(int)
    top = np.sort(price[avail])[::-1][:slots]
    extra = float((top - 1).clip(0).sum())
    scale = (money - slots) / extra if extra > 0 else 1.0
    return np.maximum(1, np.rint(1 + (price - 1).clip(0) * max(scale, 0.0))).astype(int)


def fill(values: np.ndarray, price: np.ndarray, avail: np.ndarray, slots: int, money: int) -> list[int]:
    """Best `slots` players of `avail` by `values` for at most `money` at `price`."""
    if slots <= 0:
        return []
    pool = avail[np.argsort(-values[avail])][:FILL_POOL]
    if len(pool) < slots:
        return [int(i) for i in pool]
    try:
        return [int(pool[j]) for j in knapsack(values[pool], price[pool], int(money), slots)]
    except ValueError:  # cannot afford the slots: take the cheapest
        return [int(i) for i in pool[np.argsort(price[pool])][:slots]]


def _standing(e: np.ndarray, mine: list[int], opp: np.ndarray) -> dict:
    keep = np.ones(9, dtype=bool)
    match, cat, per = _scores(e[mine].sum(axis=0)[None], opp, keep)
    return {"match": 100 * float(match[0]), "cat": 100 * float(cat[0]), "per_cat": (100 * per[0]).tolist()}


def advise(e: np.ndarray, gdol: np.ndarray, base_cost: np.ndarray, punt_dollars: dict, teams: list[Team],
           sold: set, nominated: int | None = None) -> dict:
    """See the module docstring. `punt_dollars`: build -> dollars per row (start of the build search)."""
    n = e.shape[0]
    avail = np.array([i for i in range(n) if i not in sold], dtype=int)
    money = sum(t.money for t in teams)
    slots = sum(t.slots for t in teams)
    price = live_prices(base_cost, avail, money, slots)
    me = next(t for t in teams if t.mine)

    # 2. Projection, richest first; players taken by a fill leave the pool.
    left = set(avail.tolist())
    proj: dict[int, list[int]] = {}
    for t in sorted(teams, key=lambda t: -t.money):
        f = fill(gdol, price, np.array(sorted(left), dtype=int), t.slots, t.money)
        proj[t.team_id] = t.players + f
        left -= set(f)
    others = [t for t in teams if not t.mine]
    opp = np.stack([e[proj[t.team_id]].sum(axis=0) for t in others]) if others else np.zeros((0, *e.shape[1:]))
    my_pool = avail[np.argsort(-gdol[avail])][:FILL_POOL]
    # My projection: my own fill from all players left (the others' fills are guesses, they do not block me).
    mine_proj = me.players + fill(gdol, price, my_pool, me.slots, me.money)
    proj[me.team_id] = mine_proj
    base = _standing(e, mine_proj, opp)

    # Category ranks: mean weekly category value of every projected team (TO negated: higher is better).
    means = {t.team_id: cat_moments(e[proj[t.team_id]].sum(axis=0))[0].mean(axis=0) for t in teams}
    mine_m = means[me.team_id]
    ranks = [1 + sum(1 for t in others if means[t.team_id][c] > mine_m[c]) for c in range(9)]

    # 4. Builds over my open slots.
    builds = []
    rosters: dict[str, list[int]] = {}

    def run_build(key: str, label: str, punts: tuple, starts: list[list[int]]) -> None:
        best = None
        for start in starts:
            team = optimise(e, my_pool, price, opp, punts, start, budget=me.money, max_rounds=12,
                            locked=len(me.players)) if me.slots else start
            st = _standing(e, team, opp)
            if best is None or st["match"] > best[1]["match"]:
                best = (team, st)
        team, st = best
        rosters[key] = team
        builds.append({"build": key, "label": label, "punts": list(punts), "match": round(st["match"], 1),
                       "cat": round(st["cat"], 1), "per_cat": [round(x, 1) for x in st["per_cat"]],
                       "fill": [int(i) for i in team[len(me.players):]],
                       "fill_cost": int(price[team[len(me.players):]].sum())})

    for key, (label, punts) in BUILDS.items():
        if punts:
            run_build(key, label, punts, [me.players + fill(punt_dollars.get(key, gdol), price, my_pool, me.slots, me.money)])
    # Free: from the plain fill and from the best forced build, so it is never below a forced punt.
    top = max(builds, key=lambda b: b["match"])["build"] if builds else None
    run_build("none", BUILDS["none"][0], (), [mine_proj] + ([rosters[top]] if top else []))
    builds.insert(0, builds.pop())

    # 5. Candidates: buy at the live price and refill the rest, against the best fill without him.
    def with_player(i: int, p: int) -> dict:
        rest = fill(gdol, price, my_pool[my_pool != i], me.slots - 1, me.money - p)
        return _standing(e, me.players + [i] + rest, opp)

    def without(i: int) -> dict:
        return _standing(e, me.players + fill(gdol, price, my_pool[my_pool != i], me.slots, me.money), opp)

    cands = [int(i) for i in my_pool[:CANDIDATES]]
    if nominated is not None and nominated not in cands and nominated in set(avail.tolist()):
        cands.append(nominated)
    max_bid = me.money - (me.slots - 1)
    rows = []
    if me.slots:
        for i in cands:
            p = int(price[i])
            if p > max_bid:
                continue
            st, wo = with_player(i, p), without(i)
            rows.append({"row": i, "price": p, "match_delta": round(st["match"] - wo["match"], 2),
                         "cat_delta": round(st["cat"] - wo["cat"], 2),
                         "per_cat_delta": [round(a - b, 1) for a, b in zip(st["per_cat"], wo["per_cat"])]})
        rows.sort(key=lambda r: -r["match_delta"])

    breakeven = None
    if nominated is not None and me.slots and nominated in set(avail.tolist()):
        ref = without(nominated)["match"]
        lo, hi = 0, max_bid  # largest price at which buying him beats the best fill without him; 0 = never
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if with_player(nominated, mid)["match"] >= ref - 1e-9:
                lo = mid
            else:
                hi = mid - 1
        breakeven = {"row": nominated, "price": lo, "live_price": int(price[nominated])}

    return {
        "categories": list(CATEGORIES),
        "base": {"match": round(base["match"], 1), "cat": round(base["cat"], 1),
                 "per_cat": [round(x, 1) for x in base["per_cat"]], "ranks": ranks},
        "my_fill": [int(i) for i in mine_proj[len(me.players):]],
        "builds": builds,
        "candidates": rows,
        "breakeven": breakeven,
        "price": {int(i): int(price[i]) for i in my_pool},
        "money_left": money, "open_slots": slots,
    }
