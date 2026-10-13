"""Base rates of year-over-year change in our 4 seasons: per-game value rank change by age and by team change."""
import sqlite3
from collections import Counter, defaultdict
from datetime import date
import numpy as np
from vdata import *
from cands import candidates

con = sqlite3.connect(DB)
bd = {pk: date.fromisoformat(b[:10]) for pk, b in con.execute("select id, birth_date from players where birth_date is not null")}
team = defaultdict(lambda: defaultdict(Counter))
for pk, s, t in con.execute("select player_pk, season, team from player_game_logs where season_type='regular'"):
    team[s][pk][t] += 1
usg = {(pk, s): (u, ts) for pk, s, u, ts in con.execute("select player_pk, season, usg_pct, ts_pct from player_advanced_stats")}
con.close()

vals, mins = {}, {}
for s in SEASONS:
    tot = season_totals(s)
    sub = {p: r for p, r in tot.items() if r['gp'] >= 20}
    g = candidates(sub, 'per_game', 200)['gscore (paper w)']
    order = sorted(g, key=g.get, reverse=True)
    vals[s] = {p: i + 1 for i, p in enumerate(order)}
    mins[s] = {p: r['min'] for p, r in tot.items()}

rows = []
for a, b in zip(SEASONS, SEASONS[1:]):
    for p in vals[a]:
        if p not in vals[b] or mins[a][p] < 1000 or mins[b][p] < 1000 or p not in bd:
            continue
        age = (date(int(b[:4]), 10, 1) - bd[p]).days / 365.25
        ta = team[a][p].most_common(1)[0][0]; tb = team[b][p].most_common(1)[0][0]
        rows.append(dict(p=p, age=age, change=ta != tb, d=vals[a][p] - vals[b][p], ra=vals[a][p],
                         du=(usg.get((p, b), (None, None))[0] or 0) - (usg.get((p, a), (None, None))[0] or 0) if (p, a) in usg and (p, b) in usg else None,
                         dts=(usg.get((p, b), (None, None))[1] or 0) - (usg.get((p, a), (None, None))[1] or 0) if (p, a) in usg and (p, b) in usg else None))
print('pairs with >=1000 min both seasons and gp>=20:', len(rows))
buckets = [(0, 22.5, '<=22'), (22.5, 24.5, '23-24'), (24.5, 26.5, '25-26'), (26.5, 29.5, '27-29'), (29.5, 32.5, '30-32'), (32.5, 99, '33+')]
print('\nRank change in per-game G-score (positive = improved), players ranked top 150 in the first season vs all:')
print('%-6s %4s %8s %8s %8s | %4s %8s %8s' % ('age', 'n', 'mean d', '+20 rk%', '-20 rk%', 'n150', 'mean d', '+20 rk%'))
for lo, hi, lab in buckets:
    g = [r for r in rows if lo <= r['age'] < hi]
    g150 = [r for r in g if r['ra'] <= 150]
    if not g: continue
    print('%-6s %4d %8.1f %8.0f %8.0f | %4d %8.1f %8.0f' % (lab, len(g), np.mean([r['d'] for r in g]), 100 * np.mean([r['d'] >= 20 for r in g]),
          100 * np.mean([r['d'] <= -20 for r in g]), len(g150), np.mean([r['d'] for r in g150]) if g150 else 0, 100 * np.mean([r['d'] >= 20 for r in g150]) if g150 else 0))
print('\nTeam change (modal team differs) vs stay, same age buckets, rank change and usage/TS change:')
print('%-6s %6s %4s %8s %8s %8s %8s' % ('age', 'moved', 'n', 'mean d', '+20 rk%', 'd usg', 'd TS%'))
for lo, hi, lab in buckets:
    for mv in (False, True):
        g = [r for r in rows if lo <= r['age'] < hi and r['change'] == mv]
        if len(g) < 8: continue
        gu = [r for r in g if r['du'] is not None]
        print('%-6s %6s %4d %8.1f %8.0f %8.2f %8.3f' % (lab, 'yes' if mv else 'no', len(g), np.mean([r['d'] for r in g]), 100 * np.mean([r['d'] >= 20 for r in g]),
              np.mean([r['du'] for r in gu]) if gu else 0, np.mean([r['dts'] for r in gu]) if gu else 0))
gu = [r for r in rows if r['du'] is not None and r['change']]
if gu:
    print('\nMovers: correlation of usage change with TS%% change: %.2f (n=%d); with rank change: %.2f' % (
        np.corrcoef([r['du'] for r in gu], [r['dts'] for r in gu])[0, 1], len(gu), np.corrcoef([r['du'] for r in gu], [r['d'] for r in gu])[0, 1]))
print('\nHow predictable is the change at all? Spearman(rank in season a, rank in season b) = %.2f; of the top-150 who improved 20+ ranks, share aged <=24: %.0f%%' % (
    spearman([r['ra'] for r in rows], [r['ra'] - r['d'] for r in rows]),
    100 * np.mean([r['age'] < 24.5 for r in rows if r['ra'] <= 150 and r['d'] >= 20])))
