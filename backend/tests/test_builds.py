from itertools import combinations

import numpy as np

from app.analytics.valuation.assistant import Team, advise, live_prices
from app.analytics.valuation.builds import BUILDS, knapsack, match_prob, optimise, room_prices, win_probs


def test_knapsack_matches_brute_force():
    rng = np.random.default_rng(0)
    values = rng.uniform(0, 30, 14)
    costs = rng.integers(1, 25, 14)
    best = max((c for c in combinations(range(14), 4) if costs[list(c)].sum() <= 40),
               key=lambda c: values[list(c)].sum())
    got = knapsack(values, costs, 40, 4)
    assert len(got) == 4 and costs[got].sum() <= 40
    assert abs(values[got].sum() - values[list(best)].sum()) < 1e-9


def test_match_prob_poisson_binomial():
    keep = np.ones(9, dtype=bool)
    assert abs(float(match_prob(np.full((1, 9), 0.5, dtype=np.float32), keep)[0]) - 0.5) < 1e-6
    sure = np.array([[1, 1, 1, 1, 1, 0, 0, 0, 0]], dtype=np.float32)
    assert abs(float(match_prob(sure, keep)[0]) - 1.0) < 1e-6
    # A punted category counts as lost: four sure wins plus the punted one is not a matchup win.
    punt = keep.copy()
    punt[0] = False
    assert float(match_prob(sure, punt)[0]) < 1e-6


def test_room_prices_sum_to_budget():
    rng = np.random.default_rng(1)
    g, m = rng.uniform(0, 60, 300), rng.uniform(0, 50, 300)
    p = room_prices(g, m, n_drafted=144, budget=2400.0)
    assert p.min() >= 1
    assert abs(int(np.sort(p)[::-1][:144].sum()) - 2400) < 40  # rounding


def test_live_prices_follow_money_left():
    base = np.array([50, 30, 10, 5, 1, 1])
    avail = np.arange(6)
    rich, poor = live_prices(base, avail, 120, 3), live_prices(base, avail, 60, 3)
    assert rich[0] > poor[0] and rich.min() >= 1


def _toy(n=60, weeks=4, seed=2):
    rng = np.random.default_rng(seed)
    per = rng.uniform(0.5, 1.5, (n, 1, 11)) * np.array([7, 15, 3, 4, 2, 20, 8, 5, 1, 1, 2])
    return np.repeat(per, weeks, axis=1) * 3


def test_win_probs_symmetric():
    e = _toy()
    a, b = e[:12].sum(0)[None], e[12:24].sum(0)[None]
    p, q = win_probs(a, b), win_probs(b, a)
    assert np.allclose(p + q, 1.0, atol=1e-5)


def test_optimise_keeps_locked_players_and_budget():
    e = _toy()
    costs = np.full(60, 5)
    opp = np.stack([e[12 * k:12 * (k + 1)].sum(0) for k in range(1, 4)])
    start = list(range(40, 52))
    team = optimise(e, np.arange(36, 60), costs, opp, (), start, budget=50, locked=2)
    assert team[:2] == start[:2] and len(set(team)) == 12
    assert costs[team[2:]].sum() <= 50


def test_advise_runs_on_a_partial_draft():
    e = _toy(n=180)
    g = np.linspace(40, 0, 180)
    cost = np.maximum(1, np.rint(g)).astype(int)
    teams = [Team(t, [t * 2, t * 2 + 1], 150, 10, mine=t == 0) for t in range(12)]
    sold = {i for t in teams for i in t.players}
    out = advise(e, g, cost, {}, teams, sold, nominated=30)
    assert {b["build"] for b in out["builds"]} == set(BUILDS)
    free = next(b for b in out["builds"] if b["build"] == "none")
    assert free["match"] >= max(b["match"] for b in out["builds"]) - 1e-9
    assert out["breakeven"] is not None and 0 <= out["breakeven"]["price"] <= 150 - 9
    assert all(len(b["fill"]) == 10 for b in out["builds"])
