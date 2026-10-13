"""Steelman for Minus-1 / DURANT: value when the base team punts FT%. Base = 11 players of which 5 come from the
40 worst FT-impact players of the pool (the punt core), 6 random. Opponents: random normal teams."""
import numpy as np
from vdata import *
from cands import candidates, raw_cats
from mwv import score_candidates

for season in SEASONS:
    players, weeks, W, G = weekly(season)
    tot = season_totals(season)
    idx = {p: i for i, p in enumerate(players)}
    minutes = np.array([tot.get(p, {}).get('min', 0) for p in players])
    pool = np.argsort(-minutes)[:144]
    P_, R = raw_cats(tot, 'totals')
    ft = {p: R[i][1] for i, p in enumerate(P_)}
    core = sorted(pool, key=lambda i: ft.get(players[i], 0))[:40]
    rest = [i for i in pool if i not in set(core)]
    rng = np.random.default_rng(3)
    P = len(players); acc = np.zeros(P); n = np.zeros(P)
    for c in range(400):
        base = np.concatenate([rng.choice(core, 5, replace=False), rng.choice(rest, 6, replace=False)])
        perm = rng.permutation([i for i in pool if i not in set(base)])
        opps = [perm[12 * k: 12 * (k + 1)] for k in range(11)]
        cs, ms, cc = score_candidates(W, base, opps)
        mask = np.ones(P, bool); mask[base] = False
        acc[mask] += cs[mask]; n[mask] += 1
    mw = dict(zip(players, acc / np.maximum(n, 1)))
    cands = candidates(tot, 'totals', 200)
    top = [p for p in sorted(mw, key=mw.get, reverse=True) if p in cands['z9']][:200]
    print(f'{season} punt-FT contexts, Spearman vs punt-MWV on top 200: ' + '  '.join(
        f"{k}={spearman([cands[k][p] for p in top], [mw[p] for p in top]):.3f}" for k in
        ('punt FT', 'z9', 'gscore (paper w)', 'minus1', 'g minus1', 'sqrt-skew z8 minus1', 'durant_approx (8cat minus1)', 'tanh z9 s=2.5')))
