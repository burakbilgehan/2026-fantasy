"""Step 5: preseason chain test, 2025-26. ESPN preseason projection -> candidate value -> plain dollars ->
best 12 for 200 USD at the real league prices (30 noisy draws, as the project backtest) -> all-play vs the 12 real rosters."""
import random
import numpy as np
from vdata import *
from cands import candidates
from mwv import cat_lines
from app.analytics.h2h_backtest import best_roster
from app.analytics.valuation.dollars import to_dollars

season = '2025-26'
players, weeks, W, G = weekly(season)
idx = {p: i for i, p in enumerate(players)}
pre = projection(season, 'espn')
picks = past_draft(season)
price = {pk: pr for pk, t, pr in picks if pk is not None}
rosters = {}
for pk, t, pr in picks:
    if pk in idx: rosters.setdefault(t, []).append(idx[pk])
O = cat_lines(np.stack([W[np.array(r)].sum(0) for r in rosters.values()]))  # (12, nw, 9)


def h2h(roster_pks):
    rows = [W[idx[p]] for p in roster_pks if p in idx]
    X = cat_lines(np.sum(rows, axis=0)) if rows else np.zeros_like(O[0])
    win = (X[None] > O).astype(float) + 0.5 * (X[None] == O)
    cats = win.sum(-1)
    return win.mean(), ((cats > 4.5) + 0.5 * (cats == 4.5)).mean()


rng = random.Random(17)
universe = set(pre)
draws = [{pk: max(1, round(price[pk] * rng.uniform(0.8, 1.25))) if pk in price else rng.randint(1, 3) for pk in universe} for _ in range(30)]
cands = candidates(pre, 'totals', 200)
print('Preseason test 2025-26 (ESPN projection, real league prices, 30 noisy draws). cat share | match share | at exact real prices')
res = []
for name, vals in cands.items():
    usd = to_dollars(vals, 144, 2400.0, 'plain')
    def buy(prices):
        return best_roster({p: (usd[p] + 0.01 * vals[p], prices.get(p, 1)) for p in vals}, 12, 200)
    scores = [h2h(buy(d)) for d in draws]
    one = h2h(buy(price))
    res.append((np.mean([s[0] for s in scores]), np.std([s[0] for s in scores]), np.mean([s[1] for s in scores]), one[0], name))
for c, sd, m, one, name in sorted(res, reverse=True):
    print('  %-32s %.3f (sd %.3f)  %.3f   %.3f' % (name, c, sd, m, one))
