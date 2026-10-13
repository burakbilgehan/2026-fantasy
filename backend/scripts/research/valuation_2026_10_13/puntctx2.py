"""Punt strength check: k of 11 base players from the 40 worst FT-impact players. Report the base teams' FT% win share
(mean over candidates in the pool) and the candidates' Spearman vs punt-MWV."""
import numpy as np
from vdata import *
from cands import candidates, raw_cats
from mwv import score_candidates

KEYS = ('punt FT', 'z9', 'gscore (paper w)', 'minus1', 'sqrt-skew z8 minus1', 'tanh z9 s=2.5')
for season in ('2023-24', '2025-26'):
    players, weeks, W, G = weekly(season)
    tot = season_totals(season)
    minutes = np.array([tot.get(p, {}).get('min', 0) for p in players])
    pool = np.argsort(-minutes)[:144]
    P_, R = raw_cats(tot, 'totals')
    ft = {p: R[i][1] for i, p in enumerate(P_)}
    core = sorted(pool, key=lambda i: ft.get(players[i], 0))[:40]
    rest = [i for i in pool if i not in set(core)]
    cands = candidates(tot, 'totals', 200)
    for k in (0, 5, 8, 11):
        rng = np.random.default_rng(3)
        P = len(players); acc = np.zeros(P); n = np.zeros(P); ftw = []
        for c in range(300):
            base = np.concatenate([rng.choice(core, k, replace=False), rng.choice(rest, 11 - k, replace=False)]).astype(int)
            perm = rng.permutation([i for i in pool if i not in set(base)])
            opps = [perm[12 * j: 12 * (j + 1)] for j in range(11)]
            cs, ms, cc = score_candidates(W, base, opps)
            mask = np.ones(P, bool); mask[base] = False
            acc[mask] += cs[mask]; n[mask] += 1
            ftw.append(cc[pool][:, 1].mean())
        mw = dict(zip(players, acc / np.maximum(n, 1)))
        top = [p for p in sorted(mw, key=mw.get, reverse=True) if p in cands['z9']][:200]
        print(f'{season} k={k:2d} bad-FT players in base: FT%% win share {np.mean(ftw):.2f} | ' + '  '.join(
            f"{kk}={spearman([cands[kk][p] for p in top], [mw[p] for p in top]):.3f}" for kk in KEYS))
