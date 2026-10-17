"""Best roster per build (T-030 draft plan; user decision 2026-10-17).

A build is a forced punt: the punted categories count as lost every week, so the roster must win 5 of
the categories left. "Free" forces nothing: the optimiser punts whatever it finds best. Cluster builds
follow the two category clusters of the 2026-27 projections (top 156 by G-score, verified 2026-10-17):
bigs (FG%, REB, BLK; r 0.46 to 0.61) and guards (FT% and 3PM r 0.60; AST with PTS 0.54, with STL 0.42).

Prices: the room price, not the raw market price. The raw market prices of the top 144 add up to about
1,900 USD while the room spends 2,400 (pricing.md), and an optimiser on raw prices buys every market
bargain, which a room of good managers bids up. Room price = a blend of the market price and G-score
dollars, scaled so that the top 144 add up to the league budget (assumed blend weight 0.5).

Opponents: "dealt" rooms. The best 132 players left (by G-score) are cut into tiers of 11 and every
opponent gets one random player of every tier, so each opponent is an average team of a room where all
value is spread evenly. Total value is fixed; a good drafter only gets more of it by taking it from the
others, so the average team is the right benchmark for structure (build) gains at fair prices.

Weekly noise: a category is won with probability Phi(mean gap / SD), with the weekly variances of the Sim
tab (`draftsim.NOISE`, measured on the 2024-25 and 2025-26 logs); a matchup is won when 5 or more of the 9
are won (Poisson-binomial over the per-category probabilities). Without the noise, any roster that wins 5
categories by a hair looks like a sure winner and every search ends in an extreme punt.

Search: start from a knapsack on (punt) z-score dollars at room prices, then swap one player at a time for
the candidate that raises the objective most (matchup probability + CAT_WEIGHT x category probability over
the categories not punted), within the budget, until no swap helps. Pure numpy, no DB.
"""

import numpy as np

from app.analytics.draftsim import NOISE
from app.analytics.valuation.core import CATEGORIES
from app.analytics.valuation.simulate import _I

# name -> (label, punted categories), category keys as in CATEGORIES.
BUILDS = {
    "none": ("Free (no forced punt)", ()),
    "punt_ast": ("Punt AST", ("ast",)),
    "punt_ft": ("Punt FT%", ("ft_pct",)),
    "punt_fg": ("Punt FG%", ("fg_pct",)),
    "punt_to": ("Punt TO", ("tov",)),
    "bigs": ("Bigs: punt FT% and 3PM", ("ft_pct", "tpm")),
    "guards": ("Guards: punt FG% and BLK", ("fg_pct", "blk")),
}
# Weight of the category share next to the matchup share in the objective (smooths the step function).
CAT_WEIGHT = 0.25


def room_prices(gscore_dollars: np.ndarray, market: np.ndarray, n_drafted: int = 144, budget: float = 2400.0,
                blend: float = 0.5) -> np.ndarray:
    """Integer room price per player (>= 1): blend x market + (1 - blend) x G-score dollars, scaled so the
    top n_drafted by the blend add up to the budget."""
    raw = blend * np.maximum(market, 1.0) + (1 - blend) * np.maximum(gscore_dollars, 1.0)
    top = np.sort(raw)[::-1][:n_drafted]
    scale = (budget - n_drafted) / max(float((top - 1).clip(0).sum()), 1.0)
    return np.maximum(1, np.rint(1 + (raw - 1).clip(0) * scale)).astype(int)


def knapsack(values: np.ndarray, costs: np.ndarray, budget: int, slots: int) -> list[int]:
    """Indices of exactly `slots` items with total cost <= budget and the largest sum of values.
    Costs are integers >= 1. Raises when no feasible roster exists."""
    n = len(values)
    neg = -1e18
    dp = np.full((slots + 1, budget + 1), neg)
    dp[0, :] = 0.0
    take = np.zeros((n, slots + 1, budget + 1), dtype=bool)
    for i in range(n):
        c, v = int(costs[i]), float(values[i])
        if c > budget:
            continue
        for k in range(min(i + 1, slots), 0, -1):
            cand = np.full(budget + 1, neg)
            cand[c:] = dp[k - 1, : budget + 1 - c] + v
            better = cand > dp[k]
            dp[k][better] = cand[better]
            take[i, k] = better
    if dp[slots, budget] <= neg / 2:
        raise ValueError("no roster fits the budget")
    out, k, b = [], slots, budget
    for i in range(n - 1, -1, -1):
        if k and take[i, k, b]:
            out.append(i)
            b -= int(costs[i])
            k -= 1
    return out[::-1]


def dealt_opponents(e: np.ndarray, ranked: np.ndarray, exclude: set, rng: np.random.Generator, rooms: int,
                    teams: int = 11, team_size: int = 12) -> np.ndarray:
    """Expected weekly sums (rooms x teams, W, 11) of dealt average teams built from `ranked` (row indices,
    best first) without `exclude`."""
    pool = np.array([i for i in ranked if i not in exclude])[: teams * team_size]
    tiers = pool.reshape(team_size, teams)
    out = []
    for _ in range(rooms):
        perm = np.stack([rng.permutation(t) for t in tiers]).T  # (teams, team_size)
        out.append(e[perm].sum(axis=1))
    return np.concatenate(out)


_COUNT = ("tpm", "pts", "reb", "ast", "stl", "blk", "tov")  # CATEGORIES order after the two percentages


def _erf(x: np.ndarray) -> np.ndarray:
    """Abramowitz and Stegun 7.1.26 (error below 1.5e-7)."""
    t = 1.0 / (1.0 + 0.3275911 * np.abs(x))
    y = 1.0 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * np.exp(-x * x)
    return np.sign(x) * y


def cat_moments(t: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Expected weekly sums (..., 11) -> mean and variance (..., 9) of the category values (TO negated)."""
    means, vars_ = [], []
    for mk, att in (("fgm", "fga"), ("ftm", "fta")):
        a = t[..., _I[att]]
        p = np.divide(t[..., _I[mk]], a, out=np.zeros_like(a), where=a > 0)
        means.append(p)
        vars_.append(np.divide(NOISE[mk] * np.clip(p * (1 - p), 0.0, None), a, out=np.full_like(a, 1e-4), where=a > 0))
    for k in _COUNT:
        m = t[..., _I[k]]
        means.append(-m if k == "tov" else m)
        vars_.append(NOISE[k] * np.maximum(m, 0.0))
    return np.stack(means, axis=-1), np.stack(vars_, axis=-1)


def win_probs(x: np.ndarray, opp: np.ndarray) -> np.ndarray:
    """x (C, W, 11) vs opp (N, W, 11) expected sums -> P(category won) (C, N, W, 9)."""
    mx, vx = cat_moments(x)
    mo, vo = cat_moments(opp)
    gap = mx[:, None] - mo[None]
    sd = np.sqrt(vx[:, None] + vo[None] + 1e-9)
    return (0.5 * (1.0 + _erf(gap / sd / np.sqrt(2.0)))).astype(np.float32)


def match_prob(p: np.ndarray, keep: np.ndarray) -> np.ndarray:
    """P(5 or more of 9 categories won), Poisson-binomial over the last axis; categories not kept are lost."""
    dist = np.zeros((*p.shape[:-1], 10), dtype=np.float32)
    dist[..., 0] = 1.0
    for c in np.flatnonzero(keep):
        q = p[..., c:c + 1]
        dist = np.concatenate([dist[..., :1] * (1 - q), dist[..., 1:] * (1 - q) + dist[..., :-1] * q], axis=-1)
    return dist[..., 5:].sum(-1)


def _scores(x: np.ndarray, opp: np.ndarray, keep: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """x (C, W, 11) vs opp (N, W, 11) -> (matchup probability, category probability over `keep`,
    per-category probability (C, 9)), means over opponents and weeks."""
    p = win_probs(x, opp)
    per_cat = p.mean(axis=(1, 2))
    match = match_prob(p, keep).mean(axis=(1, 2))
    return match, per_cat[:, keep].mean(-1), per_cat


def objective(match: np.ndarray, cat: np.ndarray) -> np.ndarray:
    return match + CAT_WEIGHT * cat


def optimise(e: np.ndarray, cands: np.ndarray, costs: np.ndarray, opp: np.ndarray, punts: tuple, start: list[int],
             budget: int = 200, max_rounds: int = 40, locked: int = 0) -> list[int]:
    """Swap search from `start` (row indices) over `cands`. The first `locked` players stay (players already
    bought during a draft; their price is not in `budget`). Returns the roster (row indices)."""
    keep = np.array([c not in punts for c in CATEGORIES])
    team = list(start)
    t_sum = e[team].sum(axis=0)
    best = objective(*_scores(t_sum[None], opp, keep)[:2])[0]
    for _ in range(max_rounds):
        spent = int(costs[team[locked:]].sum())
        free = np.array([c for c in cands if c not in team], dtype=int)
        move = None
        for slot in range(locked, len(team)):
            out = team[slot]
            room = budget - spent + int(costs[out])
            ok = free[costs[free] <= room]
            if not len(ok):
                continue
            sc = objective(*_scores(t_sum[None] - e[out][None] + e[ok], opp, keep)[:2])
            j = int(np.argmax(sc))
            if sc[j] > best + 1e-9:
                best, move = float(sc[j]), (slot, int(ok[j]))
        if move is None:
            break
        slot, inn = move
        t_sum = t_sum - e[team[slot]] + e[inn]
        team[slot] = inn
    return team


def team_eval(e: np.ndarray, team: list[int], opp: np.ndarray, punts: tuple = ()) -> dict:
    """Shares in percent: matchups (punted categories lost), categories (all 9), per category."""
    keep = np.array([c not in punts for c in CATEGORIES])
    t = e[team].sum(axis=0)[None]
    match, _, per = _scores(t, opp, keep)
    free_match = _scores(t, opp, np.ones(9, dtype=bool))[0]
    return {"match_share": round(100 * float(free_match[0]), 1), "forced_match_share": round(100 * float(match[0]), 1),
            "cat_share": round(100 * float(per[0].mean()), 1),
            "per_cat": dict(zip(CATEGORIES, (100 * per[0]).round(1).tolist()))}
