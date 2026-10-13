"""Step 2: static candidates (on real season totals) vs the empirical MWV, per season; DURANT family vs Lloyd."""
import numpy as np
from vdata import *
from cands import candidates
from mwv import synthetic

out = np.load('mwv.npy', allow_pickle=True).item()
nm = names()

# noise check of MWV itself
players2, cs2, _, _ = synthetic('2025-26', n_ctx=600, seed=2)
d = out['2025-26']; mw1 = dict(zip(d['players'].tolist(), d['cat'])); mw2 = dict(zip(players2, cs2))
top = sorted(mw1, key=mw1.get, reverse=True)[:200]
print('MWV seed1 vs seed2, top200 rho = %.3f' % spearman([mw1[p] for p in top], [mw2[p] for p in top]))

table = {}
for season in SEASONS + ['2025-26-real']:
    rows = season_totals(season[:7])
    d = out[season]; mw = dict(zip(d['players'].tolist(), d['cat']))
    cands = candidates(rows, 'totals', 200)
    top200 = [p for p in sorted(mw, key=mw.get, reverse=True) if p in rows and rows[p]['gp'] > 0][:200]
    gp20 = [p for p in mw if p in rows and rows[p]['gp'] >= 20]
    for name, vals in cands.items():
        r200 = spearman([vals[p] for p in top200], [mw[p] for p in top200])
        rall = spearman([vals[p] for p in gp20], [mw[p] for p in gp20])
        table.setdefault(name, {})[season] = (r200, rall)

cols = SEASONS + ['2025-26-real']
print('\nSpearman vs MWV. First number: top 200 by MWV; second: all players with GP>=20. Models on real season totals, pool 200.')
print('%-32s ' % 'model' + ' '.join('%13s' % c[2:] for c in cols) + '   mean(top200, 4 synth)')
rows_out = []
for name, per in table.items():
    mean200 = np.mean([per[s][0] for s in SEASONS])
    rows_out.append((mean200, name, per))
for mean200, name, per in sorted(rows_out, reverse=True):
    print('%-32s ' % name + ' '.join('%6.3f %6.3f' % per[c] for c in cols) + '   %.3f' % mean200)

# DURANT family vs Lloyd (per game, pool all, no GP floor), 2025-26
print('\nDURANT family, per-game basis, pool=all, vs Lloyd D (n up to 41) and vs Lloyd S:')
rows = season_totals('2025-26')
cands_pg = candidates(rows, 'per_game', None)
pk_of = {n: find_player(n, nm) for n in set(LLOYD_D) | set(LLOYD_S)}
res = []
for name, vals in cands_pg.items():
    order = sorted(vals, key=vals.get, reverse=True); rank = {p: i + 1 for i, p in enumerate(order)}
    pairs = [(LLOYD_D[n], rank[pk_of[n]]) for n in LLOYD_D if pk_of[n] in rank]
    pairsS = [(LLOYD_S[n], rank[pk_of[n]]) for n in LLOYD_S if pk_of[n] in rank]
    mad = np.mean([abs(np.log(a) - np.log(b)) for a, b in pairs])
    res.append((spearman(*zip(*pairs)), name, spearman(*zip(*pairsS)), mad, rank))
for rho, name, rhoS, mad, rank in sorted(res, reverse=True):
    print('  %-32s vs D rho=%.3f  mean|log rank diff|=%.2f   vs S rho=%.3f' % (name, rho, mad, rhoS))
print('\nKey names, Lloyd D vs our per-game ranks:')
show = ['Giannis Antetokounmpo', 'Jaylen Brown', 'Paolo Banchero', 'Stephon Castle', 'Pascal Siakam', 'Alperen Sengun', 'Chet Holmgren',
        'Jay Huff', 'Payton Pritchard', "Kel'el Ware", 'Walker Kessler', 'Onyeka Okongwu', 'Rudy Gobert', 'Jaden McDaniels']
pick = ['z9', 'durant_approx (8cat minus1)', 'sqrt-skew z8 minus1', 'sqrt-skew tanh z8 s=2 minus1', 'tanh z8 s=2 (no TO)', 'fantasy pts (yahoo)']
ranks = {name: r for _, name, _, _, r in res}
print('%-24s %4s | ' % ('player', 'L-D') + ' '.join('%8s' % n[:8] for n in pick))
for n in show:
    pk = pk_of[n]
    print('%-24s %4d | ' % (n[:24], LLOYD_D[n]) + ' '.join('%8d' % ranks[m][pk] for m in pick))

# where MWV and z9 disagree most (2025-26, top 200)
print('\n2025-26: largest rank gaps, MWV vs z9 (totals), top 200 by MWV:')
rows = season_totals('2025-26'); d = out['2025-26']; mw = dict(zip(d['players'].tolist(), d['cat']))
z9 = candidates(rows, 'totals', 200)['z9']
mwr = {p: i + 1 for i, p in enumerate(sorted(mw, key=mw.get, reverse=True))}
zr = {p: i + 1 for i, p in enumerate(sorted(z9, key=z9.get, reverse=True))}
common = [p for p in mwr if p in zr and mwr[p] <= 200]
gaps = sorted(common, key=lambda p: zr[p] - mwr[p])
for label, lst in (('MWV likes more than z9', gaps[-12:][::-1]), ('z9 likes more than MWV', gaps[:12])):
    print(' ', label)
    for p in lst:
        r = rows[p]; g = r['gp']
        print('    %-26s MWV %3d  z9 %3d  gp %2d  pts %.1f reb %.1f ast %.1f stl %.1f blk %.1f to %.1f fg%% %.3f ft%% %.3f' % (
            nm[p][:26], mwr[p], zr[p], g, r['pts']/g, r['reb']/g, r['ast']/g, r['stl']/g, r['blk']/g, r['tov']/g,
            r['fgm']/max(r['fga'],1), r['ftm']/max(r['fta'],1)))
