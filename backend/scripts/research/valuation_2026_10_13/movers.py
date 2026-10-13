"""Replicate Paine 2010 on our 4 seasons: year-to-year correlation of per-36 stats and shooting, stayers vs team changers."""
import sqlite3
from collections import Counter, defaultdict
import numpy as np
from vdata import *

con = sqlite3.connect(DB)
team = defaultdict(lambda: defaultdict(Counter))
for pk, s, t in con.execute("select player_pk, season, team from player_game_logs where season_type='regular'"):
    team[s][pk][t] += 1
ts = {(pk, s): v for pk, s, v in con.execute("select player_pk, season, ts_pct from player_advanced_stats where ts_pct is not null")}
usg = {(pk, s): v for pk, s, v in con.execute("select player_pk, season, usg_pct from player_advanced_stats where usg_pct is not null")}
con.close()
tot = {s: season_totals(s) for s in SEASONS}


def feats(p, s):
    r = tot[s][p]; m = r['min']
    f = {k: r[k] / m * 36 for k in ('pts', 'reb', 'ast', 'stl', 'blk', 'tov', 'tpm')}
    f['fg%'] = r['fgm'] / r['fga'] if r['fga'] else None
    f['ft%'] = r['ftm'] / r['fta'] if r['fta'] >= 50 else None
    f['ts%'] = ts.get((p, s)); f['usg'] = usg.get((p, s))
    return f


rows = []
for a, b in zip(SEASONS, SEASONS[1:]):
    for p in tot[a]:
        if p in tot[b] and tot[a][p]['min'] >= 1000 and tot[b][p]['min'] >= 1000 and team[a][p] and team[b][p]:
            mv = team[a][p].most_common(1)[0][0] != team[b][p].most_common(1)[0][0]
            rows.append((mv, feats(p, a), feats(p, b)))
keys = ['pts', 'reb', 'ast', 'stl', 'blk', 'tov', 'tpm', 'fg%', 'ft%', 'ts%', 'usg']
print('Year-to-year Pearson r, players with 1000+ minutes in both seasons (per-36 rates, shooting):')
print('%-8s %4s ' % ('group', 'n') + ' '.join('%6s' % k for k in keys))
for mv, lab in ((False, 'stay'), (True, 'move')):
    g = [r for r in rows if r[0] == mv]
    out = []
    for k in keys:
        pairs = [(fa[k], fb[k]) for _, fa, fb in g if fa[k] is not None and fb[k] is not None]
        out.append(np.corrcoef([x for x, _ in pairs], [y for _, y in pairs])[0, 1])
    print('%-8s %4d ' % (lab, len(g)) + ' '.join('%6.2f' % v for v in out))
