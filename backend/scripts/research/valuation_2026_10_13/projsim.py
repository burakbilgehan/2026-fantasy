"""Prototype: simulated H2H value on a PROJECTION (2025-26 ESPN preseason). Expected weekly line =
per-game projection x availability (proj GP / 82) x the team's games in that fantasy week (from the 2025-26 logs).
Deterministic (no weekly noise). Then the same preseason chain test as preseason.py."""
import random, sqlite3
from collections import Counter, defaultdict
from datetime import date, timedelta
import numpy as np
from vdata import *
from cands import candidates
from mwv import cat_lines, score_candidates
from app.analytics.h2h_backtest import best_roster
from app.analytics.valuation.dollars import to_dollars

season = '2025-26'
players, weeks, W, G = weekly(season)
widx = {w: i for i, w in enumerate(weeks)}
idx = {p: i for i, p in enumerate(players)}
con = sqlite3.connect(DB)
team_games = defaultdict(set); modal = defaultdict(Counter)
for pk, d, t in con.execute("select player_pk, game_date, team from player_game_logs where season=? and season_type='regular'", (season,)):
    d = date.fromisoformat(d[:10]); monday = d - timedelta(days=d.weekday())
    if monday in widx:
        team_games[t].add((monday, d)); modal[pk][t] += 1
con.close()
Gt = {t: np.array([sum(1 for m, d in g if m == w) for w in weeks]) for t, g in team_games.items()}
pre = projection(season, 'espn')
P = sorted(pre)
E = np.zeros((len(P), len(weeks), 11))
pmin = {}
for i, p in enumerate(P):
    r = pre[p]; gp = r['gp']
    if gp <= 0: continue
    t = modal[p].most_common(1)[0][0] if modal[p] else None
    games = Gt.get(t, np.full(len(weeks), 3.5))
    per_game = np.array([r[s] for s in STATS]) / gp
    E[i] = per_game[None, :] * (min(gp / 82, 1.0) * games)[:, None]
    pmin[p] = r['min'] * gp if r['min'] else gp
pool = np.argsort([-pmin.get(p, 0) for p in P])[:144]
rng = np.random.default_rng(5)
acc = np.zeros(len(P)); n = np.zeros(len(P))
for c in range(600):
    perm = rng.permutation(pool); base = perm[:11]
    opps = [perm[11 + 12 * k: 11 + 12 * (k + 1)] for k in range(11)]
    cs, ms, cc = score_candidates(E, base, opps)
    mask = np.ones(len(P), bool); mask[base] = False
    acc[mask] += cs[mask]; n[mask] += 1
mwv_proj = dict(zip(P, acc / np.maximum(n, 1)))

# chain test
picks = past_draft(season)
price = {pk: pr for pk, t, pr in picks if pk is not None}
rosters = {}
for pk, t, pr in picks:
    if pk in idx: rosters.setdefault(t, []).append(idx[pk])
O = cat_lines(np.stack([W[np.array(r)].sum(0) for r in rosters.values()]))
def h2h(roster_pks):
    rows = [W[idx[p]] for p in roster_pks if p in idx]
    X = cat_lines(np.sum(rows, axis=0)) if rows else np.zeros_like(O[0])
    win = (X[None] > O).astype(float) + 0.5 * (X[None] == O)
    return win.mean()
rr = random.Random(17)
draws = [{pk: max(1, round(price[pk] * rr.uniform(0.8, 1.25))) if pk in price else rr.randint(1, 3) for pk in pre} for _ in range(30)]
cands = candidates(pre, 'totals', 200)
tests = {'simulated value on projection (deterministic lines)': mwv_proj, 'gscore (paper w)': cands['gscore (paper w)'], 'z9': cands['z9'], 'minus1': cands['minus1']}
nm = names()
print('Spearman on projection, top 200 by G: sim vs G = %.3f' % spearman(*zip(*[(mwv_proj[p], cands['gscore (paper w)'][p]) for p in sorted(cands['gscore (paper w)'], key=cands['gscore (paper w)'].get, reverse=True)[:200]])))
for name, vals in tests.items():
    vals = {p: v for p, v in vals.items() if p in pre}
    usd = to_dollars(vals, 144, 2400.0, 'plain')
    def buy(prices): return best_roster({p: (usd[p] + 0.01 * vals[p], prices.get(p, 1)) for p in vals}, 12, 200)
    scores = [h2h(buy(d)) for d in draws]
    print('  %-52s cat share %.3f (sd %.3f)   at exact prices %.3f' % (name, np.mean(scores), np.std(scores), h2h(buy(price))))
top = sorted(mwv_proj, key=mwv_proj.get, reverse=True)[:12]
print('sim-on-projection top 12:', ', '.join(nm[p] for p in top))
