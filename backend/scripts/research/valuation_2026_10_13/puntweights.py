"""Which categories matter in a punt-FT build: OLS weights of the punt-MWV on the 9 z, by punt strength k."""
import numpy as np
from vdata import *
from cands import zmat, raw_cats
from mwv import score_candidates

for season in ('2023-24', '2025-26'):
    players, weeks, W, G = weekly(season)
    tot = season_totals(season)
    minutes = np.array([tot.get(p, {}).get('min', 0) for p in players])
    pool = np.argsort(-minutes)[:144]
    P_, R = raw_cats(tot, 'totals')
    ft = {p: R[i][1] for i, p in enumerate(P_)}
    core = sorted(pool, key=lambda i: ft.get(players[i], 0))[:40]
    rest = [i for i in pool if i not in set(core)]
    Pz, Z = zmat(tot, 'totals', 200); zi = {p: i for i, p in enumerate(Pz)}
    print(f'{season}: OLS weights (mean 1) of punt-MWV on z, top 250 by punt-MWV; last column = Spearman of the fitted linear model')
    print('%-5s %5s ' % ('k', 'FTwin') + ' '.join('%6s' % c[:6] for c in CATS) + '   rho_fit  rho_G  rho_z9')
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
        top = [p for p in sorted(mw, key=mw.get, reverse=True) if p in zi][:250]
        X = np.array([Z[zi[p]] for p in top]); y = np.array([mw[p] for p in top])
        A = np.hstack([X, np.ones((len(X), 1))]); w = np.linalg.lstsq(A, y, rcond=None)[0][:9]
        G_ = np.array([0.56, 0.58, 0.72, 0.65, 0.69, 0.75, 0.44, 0.68, 0.62])
        print('%-5d %5.2f ' % (k, np.mean(ftw)) + ' '.join('%6.2f' % v for v in w / w.mean()) +
              '   %.3f    %.3f  %.3f' % (spearman(X[:200] @ w, y[:200]), spearman(X[:200] @ G_, y[:200]), spearman(X[:200].sum(1), y[:200])))
